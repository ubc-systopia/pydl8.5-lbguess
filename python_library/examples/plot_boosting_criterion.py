"""
======================
Default DL85Classifier
======================

"""
import os
import warnings
from sklearn.metrics import confusion_matrix
from sklearn.exceptions import FitFailedWarning
from sklearn.model_selection import train_test_split
import sys
import time
import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import GridSearchCV
from sklearn.model_selection import KFold, StratifiedKFold, StratifiedShuffleSplit
from sklearn.model_selection import cross_val_score, cross_validate
from dl85 import DL85Booster, MODEL_LP_RATSCH, MODEL_LP_DEMIRIZ, MODEL_QP_MDBOOST, DL85Classifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, AdaBoostClassifier


VERBOSE_LEVEL = 10
MAX_ITERATIONS, TIME_LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0, 0
N_FOLDS, N_FOLDS_TUNING, MAX_DEPTH, MIN_SUP = 5, 4, int(sys.argv[1]) if len(sys.argv) > 1 else 1, 1
first_file = sys.argv[3] + '.txt' if len(sys.argv) > 3 else 'hepatitis.txt'
# python3 file.py max_depth max_iterations first_file

directory = '../datasets'
file_out = open("out_marg_maxiter_" + (str(MAX_ITERATIONS) if MAX_ITERATIONS > 0 else 'none') + "_depth_" + str(MAX_DEPTH) + ".csv", "a+")
files = ['zoo-1.txt',
         'hepatitis.txt',
         'lymph.txt',
         'audiology.txt',
         'heart-cleveland.txt',
         'primary-tumor.txt',
         'tic-tac-toe.txt',
         'vote.txt',
         'soybean.txt',
         'anneal.txt',
         'yeast.txt',
         'australian-credit.txt',
         'breast-wisconsin.txt',
         'diabetes.txt',
         'german-credit.txt',
         'kr-vs-kp.txt',
         'hypothyroid.txt',
         'mushroom.txt',
         'vehicle.txt',
         'ionosphere.txt',
         'segment.txt',
         'splice-1.txt',
         'pendigits.txt',
         'letter.txt']

for filename in files[files.index(first_file):files.index(first_file)+1]:
    dataset = np.genfromtxt("../datasets/" + filename, delimiter=' ')
    X, y = dataset[:, 1:], dataset[:, 0]

    # build training and test set for each fold
    kf = StratifiedKFold(n_splits=N_FOLDS)
    X_trains, X_tests, y_trains, y_tests = [], [], [], []
    train_indices, test_indices = [], []
    for train_index, test_index in kf.split(X, y):
        # for each fold, use 80% for training and 20% for testing
        if X.shape[0] <= 1000:
            # set training data and keep their index in initial data
            train_indices.append(train_index)
            X_trains.append(X[train_index])
            y_trains.append(y[train_index])
            # set test data and keep their index in initial data
            test_indices.append(test_index)
            X_tests.append(X[test_index])
            y_tests.append(y[test_index])
        # when the dataset size is greater than 1000, just keep randomly 800 instances from the initially 80%
        # planned for training. add the remaining to the 20% planned for testing to build the real test set
        else:
            kk = StratifiedShuffleSplit(n_splits=2, train_size=800, random_state=0)
            for tr_i, te_i in kk.split(X[train_index], y[train_index]):
                # use the train_index list and tr_i index to retrieve the training index in the initial data
                train_indices.append(train_index[tr_i])
                X_trains.append(X[train_index[tr_i]])
                y_trains.append(y[train_index[tr_i]])
                # make like for training but add test_index not involved to get the new test set
                test_indices.append(np.concatenate((train_index[te_i], test_index)))
                X_tests.append(X[np.concatenate((train_index[te_i], test_index))])
                y_tests.append(y[np.concatenate((train_index[te_i], test_index))])
                break
    # prepare the folds for grid search CV
    custom_cv_dl85 = zip(train_indices, test_indices)
    custom_cv_cart = zip(train_indices, test_indices)
    custom_cv_ada = zip(train_indices, test_indices)
    custom_cv_ada1 = zip(train_indices, test_indices)

    # describe the data
    print("Dataset :", filename)
    print("size of 0 :", y.tolist().count(0), "size of 1 :", y.tolist().count(1))
    print("n_feat = ", X.shape[1], "n_trans = ", X.shape[0])

    # write the description part of the data in the results
    to_write = [filename.split(".")[0], X.shape[1], X.shape[0], y.tolist().count(0), y.tolist().count(1)]

    parameters = {'regulator': [0.01, 0.1, 0.5, 1, 5, 8, 10, 12, 13, 15, 17, 18, 20, 30, 50, 100]}
    parameters_ratsch = {'regulator': [0.01, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1, 3, 5, 8, 10, 15]}
    parameters_ada = {'n_estimators': [10, 50, 100, 200, 500, 800, 1000]}

    print("######################################################################\n"
          "#                                START                               #\n"
          "######################################################################")

    # ========================= #
    #        Optiboost          #
    # ========================= #
    def get_ntrees(estimator, X, y):
        return estimator.n_estimators_

    def get_niterations(estimator, X, y):
        return estimator.n_iterations_

    def get_margin_score(estimator, X, y):
        assert isinstance(estimator, DL85Booster)
        # n_pos = len([marg for marg in estimator.margins_norm_ if marg >= 0])
        # # return np.array(estimator.margins_).mean() - np.array(estimator.margins_).var()
        # # return np.array(estimator.margins_norm_).mean() - np.array(estimator.margins_norm_).var()
        # return n_pos
        preds = []
        for estim in estimator.estimators_:
            preds.append([-1 if p != y[i] else 1 for i, p in enumerate(estim.predict(X))])
        preds = np.array(preds).transpose()
        weights_ = [float(i)/sum(estimator.estimator_weights_) for i in estimator.estimator_weights_]
        # weights_ = estimator.estimator_weights_[:]
        margins_ = (preds @ np.array(weights_).reshape(-1, 1)).transpose().tolist()[0]
        n_pos = len([marg for marg in estimator.margins_norm_ if marg >= 0])
        n_poss = len([marg for marg in estimator.margins_norm_ if marg > 0])
        margins_ = np.array(margins_)
        # return margins_.mean() - margins_.var()
        print("acccc", accuracy_score(y, estimator.predict(X)), "calc", n_pos / len(estimator.margins_norm_), "calcccc", n_poss / len(estimator.margins_norm_))
        return n_pos / len(estimator.margins_norm_)

    def replacenan(l):
        for i in range(len(l)):
            if np.isnan(l[i]):
                l[i] = 0
        return list(map(lambda x: str(x), l))

    # lpdem_cart_regs, lpdem_opti_regs, lprat_cart_regs, lprat_opti_regs, md_cart_regs, md_opti_regs = [], [], [], [], [], []
    # lpdem_cart_regs_score, lpdem_opti_regs_score, lprat_cart_regs_score, lprat_opti_regs_score, md_cart_regs_score, md_opti_regs_score = [], [], [], [], [], []
    # lpdem_cart_regs_trees, lpdem_opti_regs_trees, lprat_cart_regs_trees, lprat_opti_regs_trees, md_cart_regs_trees, md_opti_regs_trees = [], [], [], [], [], []
    # lpdem_cart_regs_iter, lpdem_opti_regs_iter, lprat_cart_regs_iter, lprat_opti_regs_iter, md_cart_regs_iter, md_opti_regs_iter = [], [], [], [], [], []
    # lpdem_cart_regs_marg, lpdem_opti_regs_marg, lprat_cart_regs_marg, lprat_opti_regs_marg, md_cart_regs_marg, md_opti_regs_marg = [], [], [], [], [], []
    # for name, base_clf in zip([x + " + " + y for x in ["LP_DEMIRIZ", "LP_RATSCH", "MDBOOST"] for y in ["DL85", "CART"]], [DL85Booster(base_estimator=base, max_depth=MAX_DEPTH, model=mod, max_iterations=MAX_ITERATIONS) for mod in [MODEL_LP_DEMIRIZ, MODEL_LP_RATSCH, MODEL_QP_MDBOOST] for base in [None, DecisionTreeClassifier(max_depth=MAX_DEPTH)]]):
    #     print("Optiboost + {}".format(name))
    #     print("Dataset :", filename)
    #     file = open(name.replace(" + ", "_") + "_maxiter_" + (str(MAX_ITERATIONS) if MAX_ITERATIONS > 0 else 'none') + "_depth_" + str(MAX_DEPTH) + ".csv", "a+")
    #     n_trees, fps, fns, fit_times, train_scores, test_scores, n_iter, regulators, gammas, n_opti, n_nodes = [], [], [], [], [], [], [], [], [], 0, []
    #     # build training set and validation set for the hyperparameter tuning. Use 4 folds for this task
    #     for k in range(N_FOLDS):
    #         X_train, X_test, y_train, y_test = X_trains[k], X_tests[k], y_trains[k], y_tests[k]
    #         print("Fold", k+1, "- Search for the best regulator using grid search...")
    #         print("One fold tuning")
    #         param = parameters_ratsch if "LP_RATSCH" in name else parameters
    #         custom_cv = zip([np.array(list(range(X_train.shape[0])))], [np.array(list(range(X_train.shape[0])))])
    #         gd_sr = GridSearchCV(estimator=base_clf, error_score=np.nan, param_grid=param, scoring={'marg': get_margin_score, 'ntrees': get_ntrees, 'niter': get_niterations, 'acc': 'accuracy'}, refit='marg', cv=custom_cv, n_jobs=-1, verbose=VERBOSE_LEVEL)
    #         gd_sr.fit(X_train, y_train)
    #         print("Fold", k+1, "- End {} with best regulator = {} on {}".format(name, gd_sr.best_params_["regulator"], filename))
    #         print("best estimator", gd_sr.best_estimator_)
    #         clf = gd_sr.best_estimator_
    #         y_pred = clf.predict(X_test)
    #         n_trees.append(clf.n_estimators_)
    #         fit_times.append(clf.duration_)
    #         train_scores.append(accuracy_score(y_train, clf.predict(X_train)))
    #         test_scores.append(accuracy_score(y_test, y_pred))
    #         n_iter.append(clf.n_iterations_)
    #         regulators.append(gd_sr.best_params_["regulator"])
    #         gammas.append(get_margin_score(clf, X_test, y_test))
    #         if name == "LP_DEMIRIZ + CART":
    #             lpdem_cart_regs.append(regulators[-1])
    #             lpdem_cart_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
    #             lpdem_cart_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
    #             lpdem_cart_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
    #             lpdem_cart_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
    #             file.write(filename + "," + ",".join(replacenan(lpdem_cart_regs_trees[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lpdem_cart_regs_iter[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lpdem_cart_regs_marg[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lpdem_cart_regs_score[-1])) + "\n")
    #             file.flush()
    #         elif name == "LP_DEMIRIZ + DL85":
    #             lpdem_opti_regs.append(regulators[-1])
    #             lpdem_opti_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
    #             lpdem_opti_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
    #             lpdem_opti_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
    #             lpdem_opti_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
    #             # print(replacenan(lpdem_opti_regs_trees[-1]))
    #             file.write(filename + "," + ",".join(replacenan(lpdem_opti_regs_trees[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lpdem_opti_regs_iter[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lpdem_opti_regs_marg[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lpdem_opti_regs_score[-1])) + "\n")
    #             file.flush()
    #         elif name == "LP_RATSCH + CART":
    #             lprat_cart_regs.append(regulators[-1])
    #             lprat_cart_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
    #             lprat_cart_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
    #             lprat_cart_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
    #             lprat_cart_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
    #             file.write(filename + "," + ",".join(replacenan(lprat_cart_regs_trees[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lprat_cart_regs_iter[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lprat_cart_regs_marg[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lprat_cart_regs_score[-1])) + "\n")
    #             file.flush()
    #         elif name == "LP_RATSCH + DL85":
    #             lprat_opti_regs.append(regulators[-1])
    #             lprat_opti_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
    #             lprat_opti_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
    #             lprat_opti_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
    #             lprat_opti_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
    #             file.write(filename + "," + ",".join(replacenan(lprat_opti_regs_trees[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lprat_opti_regs_iter[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lprat_opti_regs_marg[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(lprat_opti_regs_score[-1])) + "\n")
    #             file.flush()
    #         elif name == "MDBOOST + CART":
    #             md_cart_regs.append(regulators[-1])
    #             md_cart_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
    #             md_cart_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
    #             md_cart_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
    #             md_cart_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
    #             file.write(filename + "," + ",".join(replacenan(md_cart_regs_trees[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(md_cart_regs_iter[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(md_cart_regs_marg[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(md_cart_regs_score[-1])) + "\n")
    #             file.flush()
    #         elif name == "MDBOOST + DL85":
    #             md_opti_regs.append(regulators[-1])
    #             md_opti_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
    #             md_opti_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
    #             md_opti_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
    #             md_opti_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
    #             file.write(filename + "," + ",".join(replacenan(md_opti_regs_trees[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(md_opti_regs_iter[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(md_opti_regs_marg[-1])) + "\n")
    #             file.write(filename + "," + ",".join(replacenan(md_opti_regs_score[-1])) + "\n")
    #             file.flush()
    #         if "CART" in name:
    #             n_nodes.append(sum([c.tree_.node_count for c in clf.estimators_]))
    #         else:  # dl85booster with dl85
    #             n_nodes.append(clf.get_nodes_count())
    #         n_opti = n_opti + 1 if clf.optimal_ else n_opti
    #         fps.append(len([i for i in [j for j, val in enumerate(y_pred) if val == 1] if y_test[i] != 1]))
    #         fns.append(len([i for i in [j for j, val in enumerate(y_pred) if val == 0] if y_test[i] != 0]))
    #         to_write += [n_iter[-1], n_trees[-1], fit_times[-1], clf.optimal_, train_scores[-1], test_scores[-1], fps[-1], fns[-1], n_nodes[-1], regulators[-1], gammas[-1]]
    #         print("fold :", k+1, "n_trees :", n_trees[k], "train_acc :", train_scores[k], "test acc :", test_scores[k], "n_nodes :", n_nodes[k], "regu :", regulators[k], "gamma :", gammas[k], "\n")
    #     file.close()
    #     print("Model built. Avg duration of building =", round(float(np.mean(fit_times)), 4))
    #     print("Number of trees =", n_trees, np.mean(n_trees))
    #     print("Accuracy on training set =", train_scores, round(float(np.mean(train_scores)), 4))
    #     print("Accuracy on test set =", test_scores, round(float(np.mean(test_scores)), 4))
    #     print("number of optimality :", n_opti)
    #     print("list of iterations :", n_iter)
    #     print("list of time :", fit_times)
    #     print("list of regulator :", regulators)
    #     print("list of gammas :", gammas)
    #     print("list of n_nodes :", n_nodes)
    #     print("sum false positives =", sum(fps))
    #     print("sum false negatives =", sum(fns), "\n\n\n")

    lpdem_cart_regs, lpdem_opti_regs, lprat_cart_regs, lprat_opti_regs, md_cart_regs, md_opti_regs = [], [], [], [], [], []
    lpdem_cart_regs_score, lpdem_opti_regs_score, lprat_cart_regs_score, lprat_opti_regs_score, md_cart_regs_score, md_opti_regs_score = [], [], [], [], [], []
    lpdem_cart_regs_trees, lpdem_opti_regs_trees, lprat_cart_regs_trees, lprat_opti_regs_trees, md_cart_regs_trees, md_opti_regs_trees = [], [], [], [], [], []
    lpdem_cart_regs_iter, lpdem_opti_regs_iter, lprat_cart_regs_iter, lprat_opti_regs_iter, md_cart_regs_iter, md_opti_regs_iter = [], [], [], [], [], []
    lpdem_cart_regs_marg, lpdem_opti_regs_marg, lprat_cart_regs_marg, lprat_opti_regs_marg, md_cart_regs_marg, md_opti_regs_marg = [], [], [], [], [], []
    for name, base_clf in zip([x + " + " + y for x in ["LP_DEMIRIZ", "LP_RATSCH", "MDBOOST"] for y in ["DL85", "CART"]], [DL85Booster(base_estimator=base, max_depth=MAX_DEPTH, model=mod, max_iterations=MAX_ITERATIONS) for mod in [MODEL_LP_DEMIRIZ, MODEL_LP_RATSCH, MODEL_QP_MDBOOST] for base in [None, DecisionTreeClassifier(max_depth=MAX_DEPTH)]]):
        print("Optiboost 4 folds + {}".format(name))
        print("Dataset :", filename)
        file = open(name.replace(" + ", "_") + "_marg_maxiter_" + (str(MAX_ITERATIONS) if MAX_ITERATIONS > 0 else 'none') + "_depth_" + str(MAX_DEPTH) + ".csv", "a+")
        n_trees, fps, fns, fit_times, train_scores, test_scores, n_iter, regulators, gammas, n_opti, n_nodes = [], [], [], [], [], [], [], [], [], 0, []
        # build training set and validation set for the hyperparameter tuning. Use 4 folds for this task
        for k in range(N_FOLDS):
            X_train, X_test, y_train, y_test = X_trains[k], X_tests[k], y_trains[k], y_tests[k]
            print("Fold", k+1, "- Search for the best regulator using grid search...")
            print("4 folds tuning")
            param = parameters_ratsch if "LP_RATSCH" in name else parameters
            # custom_cv = zip([np.array(list(range(X_train.shape[0])))], [np.array(list(range(X_train.shape[0])))])
            gd_sr = GridSearchCV(estimator=base_clf, error_score=np.nan, param_grid=param, scoring={'marg': get_margin_score, 'ntrees': get_ntrees, 'niter': get_niterations, 'acc': 'accuracy'}, refit='marg', cv=N_FOLDS_TUNING, n_jobs=-1, verbose=VERBOSE_LEVEL)
            gd_sr.fit(X_train, y_train)
            print("Fold", k+1, "- End {} with best regulator = {} on {}".format(name, gd_sr.best_params_["regulator"], filename))
            print("best estimator", gd_sr.best_estimator_)
            clf = gd_sr.best_estimator_
            y_pred = clf.predict(X_test)
            n_trees.append(clf.n_estimators_)
            fit_times.append(clf.duration_)
            train_scores.append(accuracy_score(y_train, clf.predict(X_train)))
            test_scores.append(accuracy_score(y_test, y_pred))
            n_iter.append(clf.n_iterations_)
            regulators.append(gd_sr.best_params_["regulator"])
            gammas.append(get_margin_score(clf, X_test, y_test))
            if name == "LP_DEMIRIZ + CART":
                lpdem_cart_regs.append(regulators[-1])
                lpdem_cart_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
                lpdem_cart_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
                lpdem_cart_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
                lpdem_cart_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
                file.write(filename + "," + ",".join(replacenan(lpdem_cart_regs_trees[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lpdem_cart_regs_iter[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lpdem_cart_regs_marg[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lpdem_cart_regs_score[-1])) + "\n")
                file.flush()
            elif name == "LP_DEMIRIZ + DL85":
                lpdem_opti_regs.append(regulators[-1])
                lpdem_opti_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
                lpdem_opti_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
                lpdem_opti_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
                lpdem_opti_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
                # print(replacenan(lpdem_opti_regs_trees[-1]))
                file.write(filename + "," + ",".join(replacenan(lpdem_opti_regs_trees[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lpdem_opti_regs_iter[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lpdem_opti_regs_marg[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lpdem_opti_regs_score[-1])) + "\n")
                file.flush()
            elif name == "LP_RATSCH + CART":
                lprat_cart_regs.append(regulators[-1])
                lprat_cart_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
                lprat_cart_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
                lprat_cart_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
                lprat_cart_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
                file.write(filename + "," + ",".join(replacenan(lprat_cart_regs_trees[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lprat_cart_regs_iter[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lprat_cart_regs_marg[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lprat_cart_regs_score[-1])) + "\n")
                file.flush()
            elif name == "LP_RATSCH + DL85":
                lprat_opti_regs.append(regulators[-1])
                lprat_opti_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
                lprat_opti_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
                lprat_opti_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
                lprat_opti_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
                file.write(filename + "," + ",".join(replacenan(lprat_opti_regs_trees[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lprat_opti_regs_iter[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lprat_opti_regs_marg[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(lprat_opti_regs_score[-1])) + "\n")
                file.flush()
            elif name == "MDBOOST + CART":
                md_cart_regs.append(regulators[-1])
                md_cart_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
                md_cart_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
                md_cart_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
                md_cart_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
                file.write(filename + "," + ",".join(replacenan(md_cart_regs_trees[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(md_cart_regs_iter[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(md_cart_regs_marg[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(md_cart_regs_score[-1])) + "\n")
                file.flush()
            elif name == "MDBOOST + DL85":
                md_opti_regs.append(regulators[-1])
                md_opti_regs_score.append(gd_sr.cv_results_['mean_test_acc'])
                md_opti_regs_trees.append(gd_sr.cv_results_['mean_test_ntrees'])
                md_opti_regs_iter.append(gd_sr.cv_results_['mean_test_niter'])
                md_opti_regs_marg.append(gd_sr.cv_results_['mean_test_marg'])
                file.write(filename + "," + ",".join(replacenan(md_opti_regs_trees[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(md_opti_regs_iter[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(md_opti_regs_marg[-1])) + "\n")
                file.write(filename + "," + ",".join(replacenan(md_opti_regs_score[-1])) + "\n")
                file.flush()
            if "CART" in name:
                n_nodes.append(sum([c.tree_.node_count for c in clf.estimators_]))
            else:  # dl85booster with dl85
                n_nodes.append(clf.get_nodes_count())
            n_opti = n_opti + 1 if clf.optimal_ else n_opti
            fps.append(len([i for i in [j for j, val in enumerate(y_pred) if val == 1] if y_test[i] != 1]))
            fns.append(len([i for i in [j for j, val in enumerate(y_pred) if val == 0] if y_test[i] != 0]))
            to_write += [n_iter[-1], n_trees[-1], fit_times[-1], clf.optimal_, train_scores[-1], test_scores[-1], fps[-1], fns[-1], n_nodes[-1], regulators[-1], gammas[-1]]
            print("fold :", k+1, "n_trees :", n_trees[-1], "train_acc :", train_scores[-1], "test acc :", test_scores[-1], "n_nodes :", n_nodes[-1], "regu :", regulators[-1], "gamma :", gammas[-1], "\n")
        file.close()
        print("Model built. Avg duration of building =", round(float(np.mean(fit_times)), 4))
        print("Number of trees =", n_trees, np.mean(n_trees))
        print("Accuracy on training set =", train_scores, round(float(np.mean(train_scores)), 4))
        print("Accuracy on test set =", test_scores, round(float(np.mean(test_scores)), 4))
        print("number of optimality :", n_opti)
        print("list of iterations :", n_iter)
        print("list of time :", fit_times)
        print("list of regulator :", regulators)
        print("list of gammas :", gammas)
        print("list of n_nodes :", n_nodes)
        print("sum false positives =", sum(fps))
        print("sum false negatives =", sum(fns), "\n\n\n")

    # # ========================= #
    # #   Optiboost + other reg   #
    # # ========================= #
    # for name in [x + " + " + y for x in ["LP_DEMIRIZ", "LP_RATSCH", "MDBOOST"] for y in ["DL85", "CART"]]:
    #     print("Optiboost + other reg + {}".format(name))
    #     print("Dataset :", filename)
    #     file = open(name.replace(" + ", "_"), "a+")
    #     n_trees, fps, fns, fit_times, train_scores, test_scores, n_iter, regulators, gammas, n_opti, n_nodes = [], [], [], [], [], [], [], [], [], 0, []
    #     # build training set and validation set for the hyperparameter tuning. Use 4 folds for this task
    #     for k in range(N_FOLDS):
    #         X_train, X_test, y_train, y_test = X_trains[k], X_tests[k], y_trains[k], y_tests[k]
    #         print("Fold", k+1, "- Search for the best regulator using grid search...")
    #
    #         clf, reg = None, None
    #         if name == "LP_DEMIRIZ + CART":
    #             reg = lpdem_opti_regs[k]
    #             clf = DL85Booster(base_estimator=DecisionTreeClassifier(max_depth=MAX_DEPTH), model=MODEL_LP_DEMIRIZ, max_iterations=MAX_ITERATIONS, regulator=reg)
    #         elif name == "LP_DEMIRIZ + DL85":
    #             reg = lpdem_cart_regs[k]
    #             clf = DL85Booster(max_depth=MAX_DEPTH, model=MODEL_LP_DEMIRIZ, max_iterations=MAX_ITERATIONS, regulator=reg)
    #         elif name == "LP_RATSCH + CART":
    #             reg = lprat_opti_regs[k]
    #             clf = DL85Booster(base_estimator=DecisionTreeClassifier(max_depth=MAX_DEPTH), model=MODEL_LP_RATSCH, max_iterations=MAX_ITERATIONS, regulator=reg)
    #         elif name == "LP_RATSCH + DL85":
    #             reg = lprat_cart_regs[k]
    #             clf = DL85Booster(max_depth=MAX_DEPTH, model=MODEL_LP_RATSCH, max_iterations=MAX_ITERATIONS, regulator=reg)
    #         elif name == "MDBOOST + CART":
    #             reg = md_opti_regs[k]
    #             clf = DL85Booster(base_estimator=DecisionTreeClassifier(max_depth=MAX_DEPTH), model=MODEL_QP_MDBOOST, max_iterations=MAX_ITERATIONS, regulator=reg)
    #         elif name == "MDBOOST + DL85":
    #             reg = md_cart_regs[k]
    #             clf = DL85Booster(max_depth=MAX_DEPTH, model=MODEL_QP_MDBOOST, max_iterations=MAX_ITERATIONS, regulator=reg)
    #
    #         clf.fit(X_train, y_train)
    #         print("Fold", k+1, "- End {} with best regulator = {} on {}".format(name, reg, filename))
    #         y_pred = clf.predict(X_test)
    #         n_trees.append(clf.n_estimators_)
    #         fit_times.append(clf.duration_)
    #         train_scores.append(accuracy_score(y_train, clf.predict(X_train)))
    #         test_scores.append(accuracy_score(y_test, y_pred))
    #         n_iter.append(clf.n_iterations_)
    #         regulators.append(reg)
    #         gammas.append(-1)
    #         if "CART" in name:
    #             n_nodes.append(sum([c.tree_.node_count for c in clf.estimators_]))
    #         else:  # dl85booster with dl85
    #             n_nodes.append(clf.get_nodes_count())
    #         n_opti = n_opti + 1 if clf.optimal_ else n_opti
    #         fps.append(len([i for i in [j for j, val in enumerate(y_pred) if val == 1] if y_test[i] != 1]))
    #         fns.append(len([i for i in [j for j, val in enumerate(y_pred) if val == 0] if y_test[i] != 0]))
    #         to_write += [n_iter[-1], n_trees[-1], fit_times[-1], clf.optimal_, train_scores[-1], test_scores[-1], fps[-1], fns[-1], n_nodes[-1], regulators[-1], gammas[-1]]
    #         print("fold :", k+1, "n_trees :", n_trees[k], "train_acc :", train_scores[k], "test acc :", test_scores[k], "n_nodes :", n_nodes[k], "regu :", regulators[k], "gamma :", gammas[k], "\n")
    #     print("Model built. Avg duration of building =", round(float(np.mean(fit_times)), 4))
    #     print("Number of trees =", n_trees, np.mean(n_trees))
    #     print("Accuracy on training set =", train_scores, round(float(np.mean(train_scores)), 4))
    #     print("Accuracy on test set =", test_scores, round(float(np.mean(test_scores)), 4))
    #     print("number of optimality :", n_opti)
    #     print("list of iterations :", n_iter)
    #     print("list of time :", fit_times)
    #     print("list of regulator :", regulators)
    #     print("list of gammas :", gammas)
    #     print("list of n_nodes :", n_nodes)
    #     print("sum false positives =", sum(fps))
    #     print("sum false negatives =", sum(fns), "\n\n\n")

    file_out.write(";".join(map(lambda x: str(x), to_write)) + "\n")
    file_out.flush()
    print(to_write)
file_out.close()
