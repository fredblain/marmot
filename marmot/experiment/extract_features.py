from __future__ import print_function, division

from argparse import ArgumentParser
import yaml
import logging
import sys
import os

from marmot.experiment.import_utils import call_for_each_element, build_object, build_objects, mk_tmp_dir
from marmot.experiment.preprocessing_utils import create_contexts, tags_from_contexts, contexts_to_features, fit_binarizers, binarize, flatten
from marmot.evaluation.evaluation_utils import compare_vocabulary
from marmot.util.persist_features import persist_features
from marmot.util.generate_crf_template import generate_crf_template

logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)
logger = logging.getLogger('experiment_logger')
'''
Only feature extraction
Extract features and save in CRF++, CRFSuite or SVMLight format
'''


def main(config):
    workers = config['workers']
    tmp_dir = config['tmp_dir']
    tmp_dir = mk_tmp_dir(tmp_dir)

    # REPRESENTATION GENERATION
    # main representations (source, target, tags)
    # training
#    train_data_generators = build_objects(config['datasets']['training'])
#    train_data = {}
#    for gen in train_data_generators:
#        data = gen.generate()
#        for key in data:
#            if key not in train_data:
#                train_data[key] = []
#            train_data[key].extend(data[key])
    train_data_generator = build_object(config['datasets']['training'][0])
    train_data = train_data_generator.generate()
    dev, test = False, False
    # test
    if 'test' in config['datasets']:
        test = True
        test_data_generator = build_object(config['datasets']['test'][0])
        test_data = test_data_generator.generate()

    # dev
    if 'dev' in config['datasets']:
        dev = True
        dev_data_generator = build_object(config['datasets']['dev'][0])
        dev_data = dev_data_generator.generate()
    # additional representations
#    print("IN MAIN")
#    print(train_data['alignments_file'])
#    print(dev_data['alignments_file'])
#    print(test_data['alignments_file'])
    if 'representations' in config:
        representation_generators = build_objects(config['representations'])
    else:
        representation_generators = []
    for r in representation_generators:
        train_data = r.generate(train_data)
        if test:
            test_data = r.generate(test_data)
        if dev:
            dev_data = r.generate(dev_data)

    print("TEST DATA", test_data['alignments'][0])
    logger.info("Simple representations: {}".format(len(train_data['target'])))
    logger.info('here are the keys in your representations: {}'.format(train_data.keys()))

    # the data_type is the format corresponding to the model of the data that the user wishes to learn
    data_type = config['data_type']
    print("DATA TYPE:", data_type)
#    sys.exit()
    print("Train data: ", len(train_data['target']))
    if dev:
        print("Dev data: ", len(dev_data['target']))
    if test:
        print("Test data: ", len(test_data['target']))
    print("In different representations: ")

    for rep in train_data:
        print(rep, len(train_data[rep]))
#    print('Source dependencies: {}'.format(train_data['source_dependencies'][0]))
#    print('Target dependencies: {}'.format(train_data['target_dependencies'][0]))
#    print('Source root: {}'.format(train_data['source_root'][0]))
#    print('Target root: {}'.format(train_data['target_root'][0]))
    train_contexts = create_contexts(train_data, data_type=data_type)
    if test:
        test_contexts = create_contexts(test_data, data_type=data_type)
        logger.info('Vocabulary comparison -- coverage for test dataset: ')
        logger.info(compare_vocabulary([train_data['target'], test_data['target']]))
    if dev:
        dev_contexts = create_contexts(dev_data, data_type=data_type)
#    print("TEST CONTEXT", test_contexts[0])
    print("Train contexts: ", len(train_contexts))
    if dev:
        print("Dev contexts: ", len(dev_contexts))
    if test:
        print("Test contexts: ", len(test_contexts))
    print('Train context example: {}'.format(train_contexts[0]))


    # END REPRESENTATION GENERATION

    # FEATURE EXTRACTION
    train_tags = call_for_each_element(train_contexts, tags_from_contexts, data_type=data_type)
    if test:
        test_tags = call_for_each_element(test_contexts, tags_from_contexts, data_type=data_type)
    if dev:
        dev_tags = call_for_each_element(dev_contexts, tags_from_contexts, data_type=data_type)
    print("Train tags: ", len(train_tags))
    if dev:
        print("Dev tags: ", len(dev_tags))
    if test:
        print("Test tags: ", len(test_tags))

    logger.info('creating feature extractors...')
    feature_extractors = build_objects(config['feature_extractors'])
    if test:
        logger.info('mapping the feature extractors over the contexts for test...')
        test_features = call_for_each_element(test_contexts, contexts_to_features, [feature_extractors, workers], data_type=data_type)
        print("Test features sample: ", test_features[0])
    if dev:
        logger.info('mapping the feature extractors over the contexts for dev...')
        dev_features = call_for_each_element(dev_contexts, contexts_to_features, [feature_extractors, workers], data_type=data_type)
    logger.info('mapping the feature extractors over the contexts for train...')
    train_features = call_for_each_element(train_contexts, contexts_to_features, [feature_extractors, 1], data_type=data_type)
    print("Train features sample: ", train_features[0])

    logger.info('number of training instances: {}'.format(len(train_features)))
    if dev:
        logger.info('number of development instances: {}'.format(len(dev_features)))
    if test:
        logger.info('number of testing instances: {}'.format(len(test_features)))

    logger.info('All of your features now exist in their raw representation, but they may not be numbers yet')
    # END FEATURE EXTRACTION

    # binarizing features
    logger.info('binarization flag: {}'.format(config['features']['binarize']))
    # flatten so that we can properly binarize the features
    if config['features']['binarize'] is True:
        logger.info('Binarizing your features...')
        all_values = []
        if data_type == 'sequential':
            all_values = flatten(train_features)
        elif data_type == 'plain':
            all_values = train_features
        elif data_type == 'token':
            all_values = flatten(train_features.values())

        feature_names = [f for extractor in feature_extractors for f in extractor.get_feature_names()]
        features_num = len(feature_names)
        true_features_num = len(all_values[0])

        logger.info('fitting binarizers...')
        binarizers = fit_binarizers(all_values)
        logger.info('binarizing test data...')
        test_features = call_for_each_element(test_features, binarize, [binarizers], data_type=data_type)
        logger.info('binarizing training data...')
        # TODO: this line hangs with alignment+w2v
        train_features = call_for_each_element(train_features, binarize, [binarizers], data_type=data_type)

        logger.info('All of your features are now scalars in numpy arrays')
        logger.info('training and test sets successfully generated')

    # persisting features
    logger.info('training and test sets successfully generated')

    experiment_datasets = [{'name': 'train', 'features': train_features, 'tags': train_tags}]
    if test:
        experiment_datasets.append({'name': 'test', 'features': test_features, 'tags': test_tags})
    if dev:
        experiment_datasets.append({'name': 'dev', 'features': dev_features, 'tags': dev_tags})
    feature_names = [f for extractor in feature_extractors for f in extractor.get_feature_names()]

    persist_dir = config['persist_dir'] if 'persist_dir' in config else config['features']['persist_dir']
    persist_dir = mk_tmp_dir(persist_dir)
    persist_format = config['persist_format'] if 'persist_format' in config else config['features']['persist_format']
    logger.info('persisting your features to: {}'.format(persist_dir))
    # for each dataset, write a file and persist the features
    for dataset_obj in experiment_datasets:
#        persist_features(dataset_obj['name'], dataset_obj['features'], persist_dir, feature_names=feature_names, tags=dataset_obj['tags'], file_format=persist_format)
        persist_features(dataset_obj['name'], dataset_obj['features'], persist_dir, feature_names=feature_names, tags=dataset_obj['tags'], file_format=persist_format)
    # generate a template for CRF++ feature extractor
    feature_num = len(feature_names)
    if persist_format == 'crf++':
        generate_crf_template(feature_num, 'template', persist_dir)

    logger.info('Features persisted to: {}'.format(', '.join([os.path.join(persist_dir, nn) for nn in [obj['name'] for obj in experiment_datasets]])))


if __name__ == '__main__':

    parser = ArgumentParser()
    parser.add_argument("configuration_file", action="store", help="path to the config file (in YAML format).")
    args = parser.parse_args()
    experiment_config = {}

    # Experiment hyperparams
    cfg_path = args.configuration_file
    # read configuration file
    with open(cfg_path, "r") as cfg_file:
        experiment_config = yaml.load(cfg_file.read())
    main(experiment_config)
