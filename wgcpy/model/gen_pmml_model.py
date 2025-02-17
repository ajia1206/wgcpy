#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
@Project:       wgcpy
@File Name:     gen_pmml_model.py
@Author:        weiguang
@Date:          2021/6/28
"""
import joblib
from wgcpy.utils.ext_fn import *
from .dz_eval import *
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import VotingClassifier
from sklearn2pmml import sklearn2pmml
from sklearn.impute import SimpleImputer
from sklearn_pandas import DataFrameMapper,CategoricalImputer
from sklearn2pmml.decoration import ContinuousDomain,CategoricalDomain
from sklearn2pmml.pipeline import PMMLPipeline
from sklearn_pandas import gen_features
from sklearn.pipeline import FeatureUnion
from sklearn.preprocessing import StandardScaler,LabelBinarizer

logger = init_logger()

class genPMMLModel:
    def __init__(self, data, target, base_features):
        self.base_features = base_features
        self.train_data = data.loc[:, self.base_features]
        self.target_data = data.loc[:, target]
        self.param_dict = None
        self.pipeline_model = None
        self.numeric_feature = None
        self.category_feature = None

    def _gen_model(self, model_type, param_dict):
        '''
        生成模型
        :param model_type: str, model type
        :param param_dict: dict, the param dict of model
        :return: model
        '''
        if isinstance(param_dict, dict):
            self.param_dict = param_dict

        if model_type == 'lgb':
            model = LGBMClassifier().set_params(**self.param_dict.get('lightgbm', {}))
        elif model_type == 'voting':
            lgb_model = LGBMClassifier().set_params(**self.param_dict.get('lightgbm', {}))
            xgb_model = XGBClassifier().set_params(**self.param_dict.get('xgboost', {}))
            lr_model = LogisticRegression().set_params(**self.param_dict.get('lr', {}))
            model = VotingClassifier(estimators=[('lightgbm', lgb_model), ('xgboost', xgb_model), ('lr', lr_model)],
                                     voting='soft', weights=np.ones(3), n_jobs=3)
        else:
            raise ValueError('the type must be lgb or voting! ')
        return model


    def make_pipeline_model(self, numeric_feature, category_feature, model_type, param_dict):
        '''
        PMML模型构建
        :param numeric_feature: list or ndarray, the numeric feature of train data
        :param category_feature: list or ndarray, the category feature of train data
        :param model_type: str, the model type of train, only support lgb and voting!
        :param param_dict: dict, the param of model
        :return:
        '''
        if isinstance(numeric_feature, (list, np.ndarray)):
            self.numeric_feature = numeric_feature

        if isinstance(category_feature, (list, np.ndarray)):
            self.category_feature = category_feature

        if isinstance(param_dict, dict):
            self.param_dict = param_dict

        model = self._gen_model(model_type=model_type, param_dict=self.param_dict)
        feature_def = gen_features(
            columns=self.category_feature,
            classes=[CategoricalDomain, CategoricalImputer, LabelBinarizer]
            )
        mapper_numerical = DataFrameMapper([
                (self.numeric_feature,[ContinuousDomain(with_data=False),
                                       SimpleImputer(missing_values=np.nan, fill_value=-999, strategy="constant"),
                                       StandardScaler()])
        ])
        mapper_category = DataFrameMapper(feature_def)

        if len(self.category_feature) == 0:
            mapper = mapper_numerical
        else:
            mapper = FeatureUnion([('mapper_numerical',mapper_numerical), ('mapper_category',mapper_category)])
        self.pipeline_model = PMMLPipeline([
            ('mapper', mapper),
            ('classifier', model)
        ])
        logger.info(f'numeric features cnt: {len(self.numeric_feature)}, \t'
                    f'category features cnt: {len(self.category_feature)}')
        logger.info(f'train data shape: {self.train_data.shape}, \t'          
                    f'target data shape: {self.target_data.shape}')
        self.pipeline_model.fit(self.train_data, self.target_data)
        self.pipeline_model.verify(self.train_data.sample(n=10))


    def evaluate(self, data, target):
        '''
        模型评估
        :param data: pd.DataFrame, the data need to evaluated
        :param target: str, the name of target label
        :return: ndarray, the predict result of data
        '''
        ts_data = data.loc[:, self.base_features]
        ts_target = data.loc[:, target]
        predict_ts = self.pipeline_model.predict_proba(ts_data)[:, 1]
        auc = plot_roc_curve(y_true=ts_target, y_predict=predict_ts, return_graph=True)
        ks = plot_ks_curve(preds=predict_ts, labels=ts_target, return_graph=True)
        logger.info(f"auc:{auc}, ks:{ks}")
        return predict_ts


    def persist(self, base_dir, model_name):
        '''
        模型保存
        :param base_dir: str, the path of save model
        :param model_name: str, model name
        :return:
        '''
        joblib.dump(self.pipeline_model, os.path.join(base_dir, f"{model_name}.pkl"), compress=3)
        sklearn2pmml(self.pipeline_model, os.path.join(base_dir, f"{model_name}.pmml"), with_repr=True)

