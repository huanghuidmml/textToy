# -*- coding:utf-8 -*-
# @FileName  :__init__.py.py
# @Time      :2021/1/31 15:16
# @Author    :huanghui

import tensorflow.compat.v1 as tf
import os

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
tf.disable_v2_behavior()

from .models import (
    BertModel, ALBertModel, ElectraModel,
    NezhaModel, WoBertModel,
    SequenceClassification, MODELS, crf,
    TokenClassification, MultiLabelClassification, MLM)
from .config import (
    BaseConfig, BertConfig, ALBertConfig,
    ElectraConfig, NeZhaConfig, WoBertConfig, CONFIGS)
from .tokenizer import (
    BasicTokenizer, BertTokenizer, WoBertTokenizer,
    ALBertTokenizer, ElectraTokenizer, NeZhaTokenizer, TOKENIZERS)

from .utils import (
    devices, init_checkpoints,
    get_assignment_map_from_checkpoint, ProgressBar,
    clean_bert_model,
    set_seed)

from .optimization import (
    AdamWeightDecayOptimizer, LAMBOptimizer,
    lr_schedule, create_optimizer, create_train_op)
from .trainer import Trainer

