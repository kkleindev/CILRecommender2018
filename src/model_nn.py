"""Neural Network Model
This module can generate predictions of movie ratings
by using neural network model on top of user and item embeddings.

Example:
    Call this module as follows.
        $ python model_nn.py iterated_svd 20 "(10,)" 1000000 0.0001
    In this example predictions will be generated on top of 20 dimensional
    iterated svd embeddings, using a neural network with a single 10 node
    wide layer, 1000000 training samples and a regularization parameter of
    0.0001.

Attributes:

    SUBMISSION_FILE: Filename where predictions will be written.
    SCORE_FILE: Filename where logging of configuration and validation results
                will be written

"""

import copy
import os
import sys
from sklearn.neural_network import MLPRegressor
from sklearn.decomposition import NMF
from sklearn.decomposition import FactorAnalysis
from sklearn.decomposition import PCA
from sklearn.manifold import LocallyLinearEmbedding
from sklearn.metrics import mean_squared_error
import numpy as np
import model_iterated_svd
import model_reg_sgd
import model_sf
import utils
import utils_svd as svd

SUBMISSION_FILE = os.path.join(
    utils.ROOT_DIR, 'data/submission_nn_on_svd_80d.csv')
SCORE_FILE = os.path.join(utils.ROOT_DIR, 'analysis/nn_scores_24.csv')
ENSEMBLE = False

def get_embeddings(data_matrix, embedding_type, embedding_dimension):
    """Given imputed data, an embedding type and dimensionality, this
    function returns u embeddings and z embeddings.
    :param data:
    :param embedding_type:
    :param embedding_dimension:
    :return:
    """
    masked_data_matrix = utils.mask_validation(data_matrix, False)
    imputed_data = utils.impute_by_variance(copy.copy(masked_data_matrix))

    print("Getting embeddings using {0}".format(embedding_type))
    if embedding_type == "svd":
        return svd.get_embeddings(imputed_data, embedding_dimension)
    elif embedding_type == "iterated_svd":
        _, u_embeddings, z_embeddings = model_iterated_svd.predict_by_svd(
            masked_data_matrix, imputed_data, embedding_dimension)
    elif embedding_type == "reg_sgd":
        # TODO(heylook): Choose model parameters.
        _, u_embeddings, z_embeddings = model_reg_sgd.predict_by_sgd(
            masked_data_matrix, embedding_dimension)
    elif embedding_type == 'sf':
        # TODO(heylook): Choose model parameters.
        _, u_embeddings, z_embeddings, _, _ = model_sf.predict_by_sf(
            masked_data_matrix, embedding_dimension)
    elif embedding_type == "pca":
        model_1 = PCA(n_components=embedding_dimension)
        u_embeddings = model_1.fit_transform(imputed_data)
        z_embeddings = model_1.fit_transform(imputed_data.T)
    elif embedding_type == "lle":
        model = LocallyLinearEmbedding()
        u_embeddings = model.fit_transform(imputed_data)
        z_embeddings = model.fit_transform(imputed_data.T)
    elif embedding_type == "ids":
        uid_dimensions = len(str(imputed_data.shape[0])) - 1
        iid_dimensions = len(str(imputed_data.shape[1])) - 1
        u_embeddings = np.zeros((imputed_data.shape[0], uid_dimensions))
        z_embeddings = np.zeros((imputed_data.shape[1], iid_dimensions))
        for i in range(u_embeddings.shape[0]):
            u_embeddings[i] = i
        for i in range(z_embeddings.shape[0]):
            z_embeddings[i] = i
    else:
        if embedding_type == "nmf":
            model = NMF(n_components=embedding_dimension, init='random',
                        random_state=0)
            imputed_data = utils.clip(imputed_data)
        elif embedding_type == "fa":
            model = FactorAnalysis(n_components=embedding_dimension)

        u_embeddings = model.fit_transform(imputed_data)
        z_embeddings = model.components_
        z_embeddings = z_embeddings.T
    return u_embeddings, z_embeddings

def generate_labeled_dataset(
        u_embeddings, z_embeddings, indices, data_matrix=None):
    if data_matrix is None:
        data_matrix = np.zeros((
            u_embeddings.shape[0], z_embeddings.shape[0]))
    datapoints = []
    labels = []
    for i, j in indices:
        embeddings = np.concatenate([u_embeddings[i], z_embeddings[j]])
        rating = data_matrix[i, j]
        datapoints.append(embeddings)
        labels.append(rating)
    return np.asarray(datapoints), np.asarray(labels)

def prepare_data_for_nn(u_embeddings, z_embeddings, data_matrix,
                        n_training_samples):
    """Concatenates user embeddings and item embeddings,
    and adds corresponding rating from data matrix.
    Returns: x_train, y_train, x_validate, y_validate."""
    # TODO(kkleindev): Replace constant by variable.
    validation_indices = utils.get_validation_indices(use_three_way=False)
    observed_indices = zip(*np.nonzero(data_matrix))
    train_indices = set(observed_indices).difference(set(validation_indices))
    train_indices = list(train_indices)
    # Possibly reduce number of training samples.
    train_indices = train_indices[:n_training_samples]
    test_indices = utils.get_indices_to_predict()
    x_train, y_train = generate_labeled_dataset(
        u_embeddings, z_embeddings, train_indices, data_matrix)
    x_validate, y_validate = generate_labeled_dataset(
        u_embeddings, z_embeddings, train_indices, data_matrix)
    x_test, _ = generate_labeled_dataset(
        u_embeddings, z_embeddings, test_indices)
    y_train = np.ravel(y_train)
    y_validate = np.ravel(y_validate)
    return x_train, y_train, x_validate, y_validate, x_test

def write_nn_predictions(
        data_matrix, y_predicted, indices_to_predict=None,
        output_file=SUBMISSION_FILE):
    """ Given vector of predictions, insert predictions into data matrix.
    :param data_matrix:
    :param y_predicted:
    :param indices_to_predict:
    :return:
    """
    if indices_to_predict is None:
        indices_to_predict = utils.get_indices_to_predict()
    for i, j in enumerate(indices_to_predict):
        data_matrix[j] = y_predicted[i]
    u_embeddings, _ = get_embeddings(data_matrix, "svd", 20)
    data_matrix = utils.knn_smoothing(data_matrix, u_embeddings)
    utils.reconstruction_to_predictions(
        data_matrix, output_file, indices_to_predict)

def write_nn_score(score, embedding_type, embedding_dimensions,
                   architecture, n_training_samples, alpha):
    """ Given parameters to log, write them to file.
    :param score:
    :param embedding_type:
    :param embedding_dimensions:
    :param architecture:
    :param n_training_samples:
    :param alpha:
    :return:
    """
    with open(SCORE_FILE, 'a+') as file:
        file.write('{0}, {1}, {2}, {3}, {4}, {5}\n'.format(
            score, embedding_type, embedding_dimensions, architecture,
            n_training_samples, alpha))

def predict_by_nn(data_matrix, nn_configuration, regressor):
    """ Given data matrix as constructed from original input, imputed data as
    obtained through preprocessing, a nn_configuration and a regressor, this
    function returns a vector of predictions for unobserved entries.
    :param data_matrix:
    :param nn_configuration:
    :param regressor:
    :return:
    """
    embedding_type, embedding_dimensions, architecture, \
        n_training_samples, alpha = nn_configuration
    u_embeddings, z_embeddings = get_embeddings(
        data_matrix, embedding_type, embedding_dimensions)
    x_train, y_train, x_validate, y_validate, x_test = \
        prepare_data_for_nn(u_embeddings, z_embeddings,
                            data_matrix, n_training_samples)
    print("regressor parameters {0}".format(regressor.get_params()))
    regressor.fit(x_train, y_train)
    y_validate_hat = regressor.predict(x_validate)
    rmse = np.sqrt(mean_squared_error(y_validate, y_validate_hat))
    print("RMSE: %f" % rmse)
    write_nn_score(rmse, embedding_type, embedding_dimensions,
                   architecture, len(x_train), alpha)
    y_predicted = regressor.predict(x_test)
    return y_predicted

def main():
    """Loads data, runs preprocessing, gets embeddings, trains network, makes
    prediction, writes results.
    :return:
    """
    np.random.seed(10)
    all_ratings = utils.load_ratings()
    data_matrix = utils.ratings_to_matrix(all_ratings)

    if len(sys.argv) == 1:
        embedding_type = "nmf"
        embedding_dimensions = 10
        architecture = (7,)
        n_training_samples = 100000
        alpha = 0.001
    else:
        embedding_type = sys.argv[1]
        embedding_dimensions = int(sys.argv[2])
        architecture = eval(sys.argv[3])
        n_training_samples = int(sys.argv[4])
        alpha = float(sys.argv[5])
        print(architecture)

    if ENSEMBLE:
        architecture = (5,)
        nn_configuration = ("svd", 10, architecture, n_training_samples, alpha)
        regressor = MLPRegressor(architecture, alpha=alpha)
        prediction_1 = predict_by_nn(
            data_matrix, nn_configuration, regressor)
        architecture = (50,)
        nn_configuration = ("nmf", 100, architecture, n_training_samples, alpha)
        regressor = MLPRegressor(architecture, alpha=alpha)
        prediction_2 = predict_by_nn(
            data_matrix, nn_configuration, regressor)
        prediction, _ = np.mean([prediction_1, prediction_2], axis=0)
        write_nn_predictions(data_matrix, prediction)

    else:
        nn_configuration = (embedding_type, embedding_dimensions,
                            architecture, n_training_samples, alpha)
        regressor = MLPRegressor(architecture, alpha=alpha, warm_start=False)
        prediction = predict_by_nn(data_matrix, nn_configuration, regressor)
        write_nn_predictions(data_matrix, prediction)
        if utils.SAVE_META_PREDICTIONS:
            utils.save_ensembling_predictions(data_matrix, 'nn')

if __name__ == '__main__':
    main()
