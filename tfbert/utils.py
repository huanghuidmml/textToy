# -*- coding:utf-8 -*-
# @FileName  :utils.py
# @Time      :2021/1/31 15:24
# @Author    :huanghui
import collections
import re
import tensorflow.compat.v1 as tf
from tensorflow.python.client import device_lib
from tensorflow.python import pywrap_tensorflow
import os
import six
import numpy as np
import random
import time
from typing import List


def setup_xla_flags():
    # causes memory fragmentation for bert leading to OOM
    if os.environ.get("TF_XLA_FLAGS", None) is not None:
        try:
            os.environ["TF_XLA_FLAGS"] += " --tf_xla_enable_lazy_compilation=false"
        except:  # mpi 4.0.2 causes syntax error for =
            os.environ["TF_XLA_FLAGS"] += " --tf_xla_enable_lazy_compilation false"
    else:
        try:
            os.environ["TF_XLA_FLAGS"] = " --tf_xla_enable_lazy_compilation=false"
        except:
            os.environ["TF_XLA_FLAGS"] = " --tf_xla_enable_lazy_compilation false"


def set_seed(seed):
    '''
    随机种子设置，发现GPU上没啥用
    :param seed:
    :return:
    '''
    random.seed(seed)
    np.random.seed(seed)
    tf.set_random_seed(seed)


def gpu_is_available():
    sess_conf = tf.ConfigProto()
    sess_conf.gpu_options.allow_growth = True
    sess_conf.allow_soft_placement = True
    with tf.Session(config=sess_conf) as sess:
        local_device_protos = device_lib.list_local_devices()
        num_gpus = sum([1 for d in local_device_protos if d.device_type == 'GPU'])
    if not num_gpus:
        return False
    return True


def devices():
    sess_conf = tf.ConfigProto()
    sess_conf.gpu_options.allow_growth = True
    sess_conf.allow_soft_placement = True
    with tf.Session(config=sess_conf) as sess:
        local_device_protos = device_lib.list_local_devices()
        gpus = [d.name for d in local_device_protos if d.device_type == 'GPU']
        cpus = [d.name for d in local_device_protos if d.device_type == 'CPU']
    if not gpus:
        return cpus
    return gpus


def search_layer(layer_name):
    all_vars = tf.trainable_variables()
    for v in all_vars:
        if layer_name in v.name:
            return v
    raise ValueError(f"{layer_name} is not included in all trainable variables.")


# 自定义进度条工具
class ProgressBar:
    """
    自定义进度条工具，避免tqdm在win10下不能单行打印的问题，
    但貌似如果嵌套进度条无法打印第一个，第一个进度条会被后边的掩盖
    """

    def __init__(self, iterator, total=None, max_length=50, desc="", bar="█"):
        if total is not None:
            self.total = total
        else:
            if hasattr(iterator, "__len__"):
                self.total = len(iterator)
            else:
                self.total = None
        self.max_len = max_length
        self.iterator = iterator
        self.desc = desc
        self.bar = bar
        self.count = 0
        self.start_time = time.time()
        self.last_time = self.start_time

    def __iter__(self):
        for el in self.iterator:
            yield el
            self.count += 1
            self.last_time = time.time()
            self.refresh()

    @classmethod
    def format_time(cls, seconds):
        mins, s = divmod(int(seconds), 60)
        h, m = divmod(mins, 60)
        if h:
            return '{0:d}:{1:02d}:{2:02d}'.format(h, m, s)
        else:
            return '{0:02d}:{1:02d}'.format(m, s)

    def format_msg(self):

        msg = "\r"
        if self.desc:
            msg += self.desc + ":  "

        if self.total is not None:
            percent = int(self.count / self.total * 100)
            length = int(self.count / self.total * self.max_len)
            msg += "{}%".format(percent)
            msg += "|" + self.bar * length + " " * (
                    self.max_len - length) + "| " + "{}/{}".format(self.count, self.total)
        else:
            msg += "{} item".format(self.count)

        seconds = self.last_time - self.start_time
        if seconds != 0:
            speed = self.count / seconds

            if self.total is not None:
                remain = (self.total - self.count) / speed
                msg += " [{} : {},  {:.2f} item/s]".format(self.format_time(seconds),
                                                           self.format_time(remain), speed)
            else:
                msg += " [{},  {:.2f} item/s]".format(self.format_time(seconds), speed)
        return msg

    def set_description(self, desc):
        self.desc = desc

    def refresh(self):
        end = ""
        if self.total is not None and self.count == self.total:
            end = "\n"
        print(self.format_msg(), end=end, sep='')

    def close(self):
        pass


def gradients_assign_add(ref, value):
    if isinstance(ref, tf.IndexedSlices):
        indices = ref.indices
        values = ref.values + value.values
        return tf.IndexedSlices(values, indices, ref.dense_shape)
    else:
        return ref + value


def compute_gradients(loss, optimizer):
    all_vars = tf.trainable_variables()
    if optimizer is not None:
        grads_and_vars = optimizer.compute_gradients(
            loss, all_vars)
    else:
        grads = tf.gradients(loss, all_vars)
        grads_and_vars = list(zip(grads, all_vars))
    return grads_and_vars


def fgm(loss, grads_and_vars=None, optimizer=None, layer_name='word_embeddings', epsilon=1.):
    """
    FGM对抗训练tensorflow1.x实现
    :param loss: 原有模型损失
    :param grads_and_vars: 原有损失计算所得梯度
    :param optimizer: 优化器
    :param layer_name: 扰动的变量名
    :param epsilon: 扰动参数
    :return:
    """
    if grads_and_vars is None:
        grads_and_vars = compute_gradients(loss, optimizer)
    embeddings = search_layer(layer_name)  # 找到embedding变量

    # 计算loss对embedding的梯度
    if optimizer is not None:
        embedding_gradients_and_vars = optimizer.compute_gradients(
            loss, [embeddings])[0]
        embedding_gradients, _ = list(zip(*embedding_gradients_and_vars))
    else:
        embedding_gradients = tf.gradients(loss, [embeddings])[0]

    embedding_gradients = tf.zeros_like(embeddings) + embedding_gradients

    # 计算扰动值
    delta = epsilon * embedding_gradients / (
            tf.sqrt(tf.reduce_sum(tf.square(embedding_gradients))) + 1e-8)
    # embedding添加扰动
    embeddings.assign_add(delta)
    # 重新计算扰动后的梯度
    adv_grads_and_vars = compute_gradients(
        loss, optimizer)

    # 将扰动后得到的梯度累加到原有梯度中
    grads_and_vars = [(gradients_assign_add(grads_and_vars[i][0], adv_grads_and_vars[i][0]),
                       grads_and_vars[i][1]) for i in range(len(grads_and_vars))]

    # 删除embedding中的扰动
    embeddings.assign_sub(delta)
    return grads_and_vars


def average_grads_and_vars(tower_grads_and_vars):
    def average_dense(grad_and_vars):
        if len(grad_and_vars) == 1:
            return grad_and_vars[0][0]

        grad = grad_and_vars[0][0]
        for g, _ in grad_and_vars[1:]:
            grad += g
        return grad / len(grad_and_vars)

    def average_sparse(grad_and_vars):
        if len(grad_and_vars) == 1:
            return grad_and_vars[0][0]

        indices = []
        values = []
        for g, _ in grad_and_vars:
            indices += [g.indices]
            values += [g.values]
        indices = tf.concat(indices, 0)
        values = tf.concat(values, 0) / len(grad_and_vars)
        return tf.IndexedSlices(values, indices, grad_and_vars[0][0].dense_shape)

    average_grads_and_vars = []
    for grad_and_vars in zip(*tower_grads_and_vars):
        if grad_and_vars[0][0] is None:
            grad = None
        elif isinstance(grad_and_vars[0][0], tf.IndexedSlices):
            grad = average_sparse(grad_and_vars)
        else:
            grad = average_dense(grad_and_vars)
        # Keep in mind that the Variables are redundant because they are shared
        # across towers. So .. we will just return the first tower's pointer to
        # the Variable.
        v = grad_and_vars[0][1]
        grad_and_var = (grad, v)
        average_grads_and_vars.append(grad_and_var)
    return average_grads_and_vars


def get_assignment_map_from_checkpoint(tvars, init_checkpoint, prefix=''):
    """Compute the union of the current variables and checkpoint variables."""
    assignment_map = {}
    initialized_variable_names = {}

    name_to_variable = collections.OrderedDict()
    for var in tvars:
        name = var.name
        m = re.match("^(.*):\\d+$", name)
        if m is not None:
            name = m.group(1)
        name_to_variable[name] = var

    init_vars = tf.train.list_variables(init_checkpoint)

    assignment_map = collections.OrderedDict()
    for x in init_vars:
        (old_name, var) = (x[0], x[1])
        new_name = prefix + old_name
        if new_name not in name_to_variable:
            continue
        assignment_map[old_name] = new_name
        initialized_variable_names[new_name] = 1
        initialized_variable_names[new_name + ":0"] = 1

    return (assignment_map, initialized_variable_names)


def init_checkpoints(init_checkpoint, print_vars=True, prefix=''):
    tvars = tf.trainable_variables()
    initialized_variable_names = {}
    if init_checkpoint:
        (assignment_map, initialized_variable_names) = get_assignment_map_from_checkpoint(
            tvars,
            init_checkpoint,
            prefix=prefix)
        tf.train.init_from_checkpoint(init_checkpoint, assignment_map)

    if print_vars:
        vars_p = []
        for var in tvars:
            if var.name not in initialized_variable_names:
                vars_p.append([var.name, var.shape])

        if vars_p:
            tf.logging.info("  **** NEW Variables ****")
            init_string = ", *NOT INIT FROM CKPT*"
            for v in vars_p:
                tf.logging.info("  name = %s, shape = %s%s", v[0], v[1], init_string)
        else:
            tf.logging.info("  **** ALL Variables RESTORED ****")


def clean_bert_model(
        model_file, save_file,
        waste_name_: List[str] = None):
    '''
    将已保存的bert系列模型的优化器参数去掉
    :param model_file:  原始ckpt文件
    :param save_file: 处理后模型保存文件
    :param waste_name_: 自定义去除参数名
    :return:
    '''
    tf.reset_default_graph()
    var_list = tf.train.list_variables(model_file)
    var_values, var_dtypes = {}, {}

    waste_name = ['global_step', 'adam', 'Adam',  # for bert
                  'lamb', 'bad_steps', 'good_steps', 'loss_scale',  # for nezha
                  ]
    if isinstance(waste_name_, list):
        waste_name.extend(waste_name_)

    for (name, shape) in var_list:
        if not any(n in name for n in waste_name):
            var_values[name] = None

    reader = pywrap_tensorflow.NewCheckpointReader(model_file)
    for name in var_values:
        tensor = reader.get_tensor(name)
        var_dtypes[name] = tensor.dtype
        var_values[name] = tensor

    with tf.variable_scope(tf.get_variable_scope(), reuse=tf.AUTO_REUSE):
        tf_vars = [
            tf.get_variable(v, shape=var_values[v].shape, dtype=var_dtypes[v])
            for v in var_values
        ]
    placeholders = [tf.placeholder(v.dtype, shape=v.shape) for v in tf_vars]
    assign_ops = [tf.assign(v, p) for (v, p) in zip(tf_vars, placeholders)]

    saver = tf.train.Saver(tf.all_variables())

    with tf.Session() as sess:
        sess.run(tf.initialize_all_variables())
        for p, assign_op, (name, value) in zip(placeholders, assign_ops,
                                               six.iteritems(var_values)):
            sess.run(assign_op, {p: value})

        # Use the built saver to save the averaged checkpoint.
        saver.save(sess, save_file)
