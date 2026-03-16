import logging
import os
from colorlog import ColoredFormatter
from global_config import global_config

lib_name = global_config.lib_name
log_path = global_config.log_path
# 配置日志记录器
def setup_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)  # 设置日志级别为DEBUG
    if not os.path.exists(log_path):
        os.makedirs(log_path)  
    # 创建一个文件处理器，并设置级别为DEBUG
    file_handler = logging.FileHandler(os.path.join(log_path, 'api_fuzz.log'))
    file_handler.setLevel(logging.DEBUG)

    # 创建日志格式器，并设置颜色
    formatter = ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        reset=True,
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )

    # 设置日志格式
    file_handler.setFormatter(formatter)

    # 给日志记录器添加处理器
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()