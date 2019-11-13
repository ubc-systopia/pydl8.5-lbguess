//
// Created by Gael Aglin on 2019-10-25.
//

#include "lcm_iterative.h"
#include "query_best.h" // if cannot link is specified, we need a clustering problem!!!
#include "logger.h"
#include <iostream>
#include <limits.h>
#include <cassert>
#include <cmath>
#include <map>
#include <unordered_set>
#include <unordered_map>
#include "dataContinuous.h"


struct Hash {
    size_t operator() (const int &vec) const {
        //                                           ^^^^^
        //                                           Don't forget this!
        return vec;
    }
};

LcmIterative::LcmIterative ( Data *data, Query *query, Trie *trie, bool infoGain, bool infoAsc, bool allDepths):
        data ( data ), query ( query ), trie ( trie ), infoGain ( infoGain ), infoAsc ( infoAsc ), allDepths ( allDepths ) {
}

LcmIterative::~LcmIterative() {
}

TrieNode* LcmIterative::recurse ( Array<Item> itemset_,
                               Item added,
                               Array<pair<bool,Attribute > > a_attributes,
                               Array<Transaction> a_transactions,
                               Depth depth,
                               Error parent_ub,
                               Depth currentMaxDepth) {
    //cout << "current max depth = " << currentMaxDepth << endl;
    Logger::showMessageAndReturn("-----------\t------------");
    Logger::showMessageAndReturn("\t\tAppel recursif. CMD : ", currentMaxDepth);

    if ( query->timeLimit > -1 ){
        float runtime = ( clock () - query->startTime ) / (float) CLOCKS_PER_SEC;
        if( runtime >= query->timeLimit )
            query->timeLimitReached = true;
    }

    Array<Item> itemset;
    itemset.alloc ( itemset_.size + 1 );

    if (added != NO_ITEM)
        addItem ( itemset_, added, itemset );
    else
        itemset = itemset_;

    Logger::showMessage("\nitemset avant ajout : ");
    printItemset(itemset_);
    Logger::showMessageAndReturn("Item à ajouter : ", added);
    Logger::showMessage("itemset après ajout : ");
    printItemset(itemset);

    TrieNode *node = trie->insert ( itemset );

    if (node->data) {//node already exists
//        if last solution can be used, we will return it. Otherwise, we will continue the search
        Logger::showMessageAndReturn("le noeud exists");

        Error leafError = ( (QueryData_Best*) node->data )->leafError;
        Error* nodeError = &( ( (QueryData_Best*) node->data )->error );
        Error storedInitUb = ( (QueryData_Best*) node->data )->initUb;
        //Error initUb = min(parent_ub, leafError);
        //Error initUb = min(parent_ub, lastBest);
        Error initUb = parent_ub;
        Depth* solDepth = &( (QueryData_Best*) node->data )->solutionDepth;

        if( *nodeError < FLT_MAX && currentMaxDepth == *solDepth ) { //if( nodeError != FLT_MAX ) best solution has been already found
            Logger::showMessageAndReturn("solution avait été trouvée pour cette profondeur ", currentMaxDepth, " et vaut : ", *nodeError);
            return node;
        }

        if (!nps)
            if ( initUb <= storedInitUb && currentMaxDepth == *solDepth ) { //solution has not been found last time but the result is the same for this time
                Logger::showMessageAndReturn("y'avait pas de solution pour cette profonceur ", currentMaxDepth, " mais c'est pareil cette fois-ci. Ancien init =",
                                             storedInitUb, " et nouveau = ", initUb);
                return node;
            }

        if ( leafError == 0 ){ // if we have a node already visited with lErr = 0, we can return the last solution
            Logger::showMessageAndReturn("l'erreur est nulle");
            return node;
        }

        if ( depth == currentMaxDepth){// query->maxdepth ){
            Logger::showMessageAndReturn("on a atteint la profondeur maximale pour cette itération. parent boud = ", parent_ub, " et leaf error = ", leafError);

            if ( parent_ub < leafError ){
                *nodeError = FLT_MAX;
                Logger::showMessageAndReturn("pas de solution");
            }
            else{
                *nodeError = leafError;
                Logger::showMessageAndReturn("on retourne leaf error = ", leafError);
            }
            return node;
        }
    }

    //there are two cases in which the execution attempt here
    //1- when the node did not exist
    //2- when the node exists but without solution for this depth
    //3- when the node exits for this depth but init value of upper bound is higher than the last one and last solution is NO_TREE

    // allocate itemset info
    Array<pair<bool,Attribute> > a_attributes2;
    Error initUb = FLT_MAX;


    if ( !node->data || (node->data && ( (QueryData_Best*) node->data )->solutionDepth < currentMaxDepth) ){
        // case 1 : when the node did not exist and
        // case 2 : when the node exists but without solution for this depth

        if (!node->data){ //node did not exist
            Logger::showMessageAndReturn("Nouveau noeud");
            closedsize++;
//            if ( closedsize % 1000 == 0 )
//                cerr << "--- Searching, lattice size: " << closedsize << "\r" << flush;

            //STEP 1 : count supports
            //<=================== START STEP 1 ===================>
            //declare variable of pair type to keep firstly an array of support per class and second the support of the itemset
            pair<Supports,Support> itemsetSupport;
            //allocate memory for the array
            itemsetSupport.first = newSupports ();
            //put all value to 0 in the array
            zeroSupports ( itemsetSupport.first );
            //count support for the itemset for each class
            forEach ( j, a_transactions ){
                ++itemsetSupport.first[data->targetClass( a_transactions[j] )];
            }
            //compute the support of the itemset
            itemsetSupport.second = sumSupports(itemsetSupport.first);
            //<===================  END STEP 1  ===================>

            //STEP 2 : call initData of query
            //<=================== START STEP 2 ===================>
            //cout << "step 2" << endl;
            Error bound = parent_ub;
            node->data = query->initData( itemsetSupport, bound, query->minsup, currentMaxDepth );

            //initialize the bound. it will be used for children in for loop
            initUb = ((QueryData_Best*) node->data)->initUb;

            Logger::showMessageAndReturn("après initialisation du nouveau noeud. parent bound = ", parent_ub, " et leaf error = ", ((QueryData_Best*) node->data)->leafError, " init bound = ", initUb, " et solution depth = ", ((QueryData_Best*) node->data)->solutionDepth);
            //<===================  END STEP 2  ===================>


            //STEP 3 : Case in which we cannot split more
            //cout << "current depth = " << depth << " and current max depth = " << currentMaxDepth << endl;
            //<=================== START STEP 3 ===================>
            if ( ((QueryData_Best*) node->data)->leafError == 0 ){
                //when leaf error equals 0 all solution parameters have already been stored by initData apart from node error
                ((QueryData_Best*) node->data)->error = ((QueryData_Best*) node->data)->leafError;
                //((QueryData_Best*) node->data)->solutionDepth = currentMaxDepth;
                Logger::showMessageAndReturn("l'erreur est nulle. node error = leaf error = ", ((QueryData_Best*) node->data)->error);
                return node;
            }

            if ( depth == currentMaxDepth){// query->maxdepth ){
                Logger::showMessageAndReturn("on a atteint la profondeur maximale pour cette itération. parent bound = ", parent_ub, " et leaf error = ", ((QueryData_Best*) node->data)->leafError);

                //((QueryData_Best*) node->data)->solutionDepth = currentMaxDepth;

                if ( parent_ub < ((QueryData_Best*) node->data)->leafError ){
                    ((QueryData_Best*) node->data)->error = FLT_MAX;
                    Logger::showMessageAndReturn("pas de solution");
                }
                else{
                    ((QueryData_Best*) node->data)->error = ((QueryData_Best*) node->data)->leafError;
                    Logger::showMessageAndReturn("on retourne leaf error = ", ((QueryData_Best*) node->data)->leafError);
                }
                return node;
            }

            if ( query->timeLimitReached ){
                ((QueryData_Best*) node->data)->error = ((QueryData_Best*) node->data)->leafError;
                return node;
            }
            //<===================  END STEP 3  ===================>
            deleteSupports(itemsetSupport.first);
        }

        else{
            Logger::showMessageAndReturn("Le noeud existe mais il n'y a pas de solution à cette profondeur");
            Error bound = min(parent_ub, ( (QueryData_Best*) node->data )->error );
            ((QueryData_Best*) node->data)->initUb = bound;
            ((QueryData_Best*) node->data)->solutionDepth = currentMaxDepth;
            initUb = ((QueryData_Best*) node->data)->initUb;
            Logger::showMessageAndReturn("cette fois-ci parent bound = ", parent_ub, " et leaf error = ", ((QueryData_Best*) node->data)->leafError, " init bound = ", initUb, " et solution depth = ", ((QueryData_Best*) node->data)->solutionDepth);

            if ( query->timeLimitReached ){
                ((QueryData_Best*) node->data)->error = ((QueryData_Best*) node->data)->leafError;
                return node;
            }
        }


        //STEP 4 : determine successors
        //<=================== START STEP 4 ===================>
        a_attributes2 = getSuccessors(a_attributes, a_transactions, added);
        //((QueryData_Best*) node->data)->children = a_attributes2;
        //<===================  END STEP 4  ===================>
    }

    else {//case 2 : when the node exists but init value of upper bound is higher than the last one and last solution is NO_TREE
        Error storedInit = ((QueryData_Best*) node->data)->initUb;
        //initUb = min(parent_ub, ((QueryData_Best*) node->data)->leafError);
        initUb = parent_ub;
        ((QueryData_Best*) node->data)->initUb = initUb;
        Logger::showMessageAndReturn("noeud existant pour cette profondeur, sans solution avec nvelle init bound. leaf error = ", ((QueryData_Best*) node->data)->leafError, " last time: error = ", ((QueryData_Best*) node->data)->error, " and init = ", ((QueryData_Best*) node->data)->initUb, " and stored init = ", storedInit);


        //IF TIMEOUT IS REACHED
        //<=================== START STEP 3 ===================>
        if ( query->timeLimitReached ){
            if ( ((QueryData_Best*) node->data)->error == FLT_MAX )
                ((QueryData_Best*) node->data)->error = ((QueryData_Best*) node->data)->leafError;
            return node;
        }

        //<===================  END STEP  ===================>


        //ONLY STEP : determine successors
        //<=================== START STEP ===================>
        //a_attributes2 = ((QueryData_Best*) node->data)->children;
        a_attributes2 = getSuccessors(a_attributes, a_transactions, added);
        //<===================  END STEP  ===================>
    }


    Error ub = initUb;
    //run for successors
    Array<Transaction> a[2]; // might allocate more than necessary, as we know that the union of a[0] and a[1] is a_transactions
    // we could even optimize by reordering the previous array to avoid allocating additional memory at all.
    // the order is not important, after all. (but could destroy cache locality)
    a[0].alloc ( ((QueryData_Best*) node->data)->nTransactions );
    a[1].alloc ( ((QueryData_Best*) node->data)->nTransactions );


    do {
        if (depth == 0){
            Logger::showMessageAndReturn("======================================>");
            Logger::showMessageAndReturn("\t\t\tNew iteration. Current Max Depth : ", currentMaxDepth);
        }

        int count = 0;
        forEach (i, a_attributes2) {
            if (a_attributes2[i].first) {
                count++;
                // build occurrence list for positive and negative
                a[0].resize(0);
                a[1].resize(0);
                forEach (j, a_transactions)a[data->isIn(a_transactions[j], a_attributes2[i].second)].push_back(
                            a_transactions[j]);

                TrieNode *left = recurse(itemset, item(a_attributes2[i].second, 0), a_attributes2, a[0], depth + 1, ub,
                                         currentMaxDepth);

                if (query->canimprove(left->data, ub)) {

                    float remainUb = ub - ((QueryData_Best *) left->data)->error;
                    TrieNode *right = recurse(itemset, item(a_attributes2[i].second, 1), a_attributes2, a[1], depth + 1,
                                              remainUb, currentMaxDepth);

                    Error feature_error =
                            ((QueryData_Best *) left->data)->error + ((QueryData_Best *) right->data)->error;
                    bool hasUpdated = query->updateData(node->data, ub, a_attributes2[i].second, left->data,
                                                        right->data);
                    if (hasUpdated) {
                        ub = feature_error - 1;
                        Logger::showMessageAndReturn("après cet attribut, node error = ",
                                                     ((QueryData_Best *) node->data)->error, " et ub = ", ub);
                    }

                    if (query->canSkip(node->data)) {//lowerBound
                        //                    if (((QueryData_Best*) node->data )->lowerBound > 0)
                        //                        cout << "lower = " << ((QueryData_Best*) node->data )->lowerBound << endl;
                        Logger::showMessageAndReturn("C'est le meilleur. on break le reste");
                        break; //prune remaining attributes not browsed yet
                    }
                }

            }
        }
        if (count == 0) {
            Logger::showMessageAndReturn("pas d'enfant.");
            if (parent_ub < ((QueryData_Best *) node->data)->leafError) {
                ((QueryData_Best *) node->data)->error = FLT_MAX;
                Logger::showMessageAndReturn("pas de solution");
            } else {
                ((QueryData_Best *) node->data)->error = ((QueryData_Best *) node->data)->leafError;
                Logger::showMessageAndReturn("on retourne leaf error = ", ((QueryData_Best *) node->data)->leafError);
            }
            Logger::showMessageAndReturn("on replie");
        }
        Logger::showMessageAndReturn("depth = ", depth, " and init ub = ", initUb, " and error after search = ",
                                     ((QueryData_Best *) node->data)->error);

        if (depth == 0){
            //cerr << "test" << endl;
            //cout << "\n\n===============================\n"
            //        "%%%%%%%%%%%% HERE %%%%%%%%%%%%%\n"
            //        "===============================" << endl;
            Logger::showMessageAndReturn("Apres l'itération de la profondeur ", currentMaxDepth, ", l'erreur obtenue est : ", ((QueryData_Best *) node->data)->error);
            currentMaxDepth += 1;
            ub = ((QueryData_Best *) node->data)->error;

            if (currentMaxDepth == query->maxdepth && query->maxError > 0) //maxErrror is used as bound for the last iteration
                ub = min(ub,query->maxError);
        }
    }while (depth == 0 && currentMaxDepth <= query->maxdepth);


    //a_attributes2.free();
    if (itemset.size > 0)
        itemset.free();
    //if (!support.first)
    //deleteSupports(support.first);

    return node;
}


void LcmIterative::run () {
    query->setStartTime( clock() );
    Array<Item> itemset; //array of items representing an itemset
    Array<pair<bool, Attribute> > a_attributes;
    Array<Transaction> a_transactions;

    itemset.size = 0;

    a_attributes.alloc ( nattributes );
    forEach ( i, a_attributes ) a_attributes[i] = make_pair ( true, i );
    a_transactions.alloc ( data->getNTransactions() );
    forEach ( i, a_transactions ) a_transactions[i] = i;

    query->realroot = recurse ( itemset, NO_ITEM, a_attributes, a_transactions, 0, NO_ERR, 1);

    /*Error currentLastBest = NO_ERR;
    Depth currentMaxDepth = 0;
    do{
        trie = new Trie;
        currentMaxDepth += 1;
        //recurse ( Array<Item> itemset_,Item added,Array<pair<bool,Attribute > > a_attributes,
        // Array<Transaction> a_transactions,Depth depth,Error parent_ub,Depth currentMaxDepth,Error lastBest)
        query->realroot = recurse ( itemset, NO_ITEM, a_attributes, a_transactions, 0, NO_ERR, currentMaxDepth, currentLastBest );
        currentLastBest = ((QueryData_Best*) query->realroot->data)->error;
        cout << "après iteration current max depth = " << currentMaxDepth << endl;
        cout << "apreès iteration current best is " << currentLastBest << endl;
    }while (currentMaxDepth < query->maxdepth);*/

    a_attributes.free ();
    a_transactions.free ();
}


float LcmIterative::informationGain ( pair<Supports,Support> notTaken, pair<Supports,Support> taken){

    int sumSupNotTaken = notTaken.second;
    int sumSupTaken = taken.second;
    int actualDBSize = sumSupNotTaken + sumSupTaken;

    float condEntropy = 0, baseEntropy = 0;
    float priorProbNotTaken = (actualDBSize != 0) ? (float)sumSupNotTaken/actualDBSize : 0;
    float priorProbTaken = (actualDBSize != 0) ? (float)sumSupTaken/actualDBSize : 0;
    float e0 = 0, e1 = 0;

    for (int j = 0; j < data->getNClasses(); ++j) {
        float p = (sumSupNotTaken != 0) ? (float)notTaken.first[j] / sumSupNotTaken : 0;
        float newlog = (p > 0) ? log2(p) : 0;
        e0 += -p * newlog;

        p = (float)taken.first[j] / sumSupTaken;
        newlog = (p > 0) ? log2(p) : 0;
        e1 += -p * newlog;

        p = (float)(notTaken.first[j] + taken.first[j]) / actualDBSize;
        newlog = (p > 0) ? log2(p) : 0;
        baseEntropy += -p * newlog;
    }
    condEntropy = priorProbNotTaken * e0 + priorProbTaken * e1 ;

    float actualGain = baseEntropy - condEntropy ;

    return actualGain; //most error to least error when it will be put in the map. If you want to have the reverse, just return the negative value of the entropy
    //return condEntropy;
}

Array<pair<bool,Attribute> > LcmIterative::getSuccessors(Array<pair<bool,Attribute >> a_attributes,
                                                      Array<Transaction> a_transactions,
                                                      Item added){

    std::multimap<float , pair<bool,Attribute> > gain;
    Array<pair<bool,Attribute>> a_attributes2 ( a_attributes.size, 0 );
    pair<Supports,Support> supports[2];
    // in principle, we have already computed this support before; however, we want to avoid
    // allocating additional memory for storing the additional supports, and therefore
    // will recompute supports here for the itemset "itemset \cup added".

    //supports[0] for item value = 0 (not taken)
    //supports[1] for item value = 1 (taken)
    supports[0].first = newSupports ();
    supports[1].first = newSupports ();

    map<int, unordered_set<int, Hash >> control;
    map<int, unordered_map<int, pair<int,float>, Hash>> controle;

    forEach ( i, a_attributes ) {
        if (item_attribute (added) == a_attributes[i].second)
            continue;
        else if (a_attributes[i].first) {
            zeroSupports(supports[0].first);
            zeroSupports(supports[1].first);


            forEach (j, a_transactions) {
                ++supports[data->isIn(a_transactions[j],a_attributes[i].second )].first[data->targetClass( a_transactions[j] )];
            }

            supports[0].second = sumSupports(supports[0].first);
            supports[1].second = sumSupports(supports[1].first);

            if (query->is_freq(supports[0]) && query->is_freq(supports[1])) {

                /*if (query->continuous){
                    //cout << "item feat size = " << attrFeat.size() << endl;

                    int sizeBefore = int(control[attrFeat[a_attributes[i].second]].size());
                    control[attrFeat[a_attributes[i].second]].insert(supports[0].second);
                    int sizeAfter = int(control[attrFeat[a_attributes[i].second]].size());

                    if (sizeAfter != sizeBefore) {
                        if (infoGain)
                            gain.insert(std::pair<float, pair<bool, Attribute>>(informationGain(supports[0], supports[1]),make_pair(true, a_attributes[i].second)));
                        else a_attributes2.push_back(make_pair(true, a_attributes[i].second));
                    } else {

                        if (infoGain)
                            gain.insert(std::pair<float, pair<bool, Attribute>>(informationGain(supports[0], supports[1]),make_pair(false, a_attributes[i].second)));
                        else a_attributes2.push_back(make_pair(false, a_attributes[i].second));
                    }

                }*/
                if (query->continuous){//continuous dataset

                    //when heuristic is used to reorder attribute, use a policy to always select the same attribute
                    if (infoGain){
                        //attribute for this feature did not exist with these transactions
                        if (controle[attrFeat[a_attributes[i].second]].count(supports[0].second) == 0)
                            gain.insert(std::pair<float, pair<bool, Attribute>>(informationGain(supports[0], supports[1]),make_pair(true, a_attributes[i].second)));
                        else
                            //attribute of this feature exist with these transactions and the existing attribute is the relevant (low index)
                        if (controle[attrFeat[a_attributes[i].second]][supports[0].second].first < a_attributes[i].second)
                            gain.insert(std::pair<float, pair<bool, Attribute>>(controle[attrFeat[a_attributes[i].second]][supports[0].second].second,make_pair(false, a_attributes[i].second)));
                        else{
                            //attribute of this feature exist with these transactions but this one is more relevant (low index)
                            for (auto itr = gain.find(controle[attrFeat[a_attributes[i].second]][supports[0].second].second); itr != gain.end(); itr++)
                                if (itr->second.second == controle[attrFeat[a_attributes[i].second]][supports[0].second].first){
                                    itr->second.first = false;
                                    gain.insert(std::pair<float, pair<bool, Attribute>>(itr->first,make_pair(true, a_attributes[i].second)));
                                    break;
                                }
                        }
                    } else{ //when there is not heuristic

                        int sizeBefore = int(control[attrFeat[a_attributes[i].second]].size());
                        control[attrFeat[a_attributes[i].second]].insert(supports[0].second);
                        int sizeAfter = int(control[attrFeat[a_attributes[i].second]].size());

                        a_attributes2.push_back(make_pair(sizeAfter != sizeBefore, a_attributes[i].second));
                    }
                }
                else {

                    if (infoGain)
                        gain.insert(std::pair<float, pair<bool, Attribute>>(informationGain(supports[0], supports[1]),make_pair(true, a_attributes[i].second)));
                    else a_attributes2.push_back(make_pair(true, a_attributes[i].second));

                }

            } else {
                if (infoGain)
                    gain.insert(std::pair<float, pair<bool, Attribute>>(NO_GAIN, make_pair(false,
                                                                                           a_attributes[i].second)));
                else a_attributes2.push_back(make_pair(false, a_attributes[i].second));
            }

        } else {
            if (infoGain)
                gain.insert(
                        std::pair<float, pair<bool, Attribute>>(NO_GAIN, make_pair(false, a_attributes[i].second)));
            else a_attributes2.push_back(a_attributes[i]);
        }
    }


    if (infoGain){
        cout << "info" << endl;
        if (infoAsc){ //items with low IG first
            multimap<float, pair<bool, int>>::iterator it;
            for( it = gain.begin(); it != gain.end(); ++it ){
                a_attributes2.push_back(it->second);
            }
        } else { //items with high IG first
            multimap<float, pair<bool, int>>::reverse_iterator it;
            for( it = gain.rbegin(); it != gain.rend(); ++it ){
                a_attributes2.push_back(it->second);
            }
        }

    }
    if (!allDepths)
        infoGain = false;

    deleteSupports(  supports[0].first );
    deleteSupports(  supports[1].first );

    return a_attributes2;

}

void LcmIterative::printItemset(Array<Item> itemset){
    if (verbose){
        for (int i = 0; i < itemset.size; ++i) {
            cout << itemset[i] << ",";
        }
        cout << endl;
    }
}