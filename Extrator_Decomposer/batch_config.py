class BatchConfig:
    def __init__(
        self,
        batch_size: int = 40,
        max_memory_gb: float = 50,
        memory_cleanup_threshold: float = 40,
        batch_wait_time: int = 5
    ):
        """
        :param batch_size: 每批处理的文件数
        :param max_memory_gb: 最大内存限制（GB）
        :param memory_cleanup_threshold: 触发内存清理的阈值（GB）
        :param batch_wait_time: 内存高时批次间等待时间（秒）
        """
        self._batch_size = batch_size
        self.max_memory_gb = max_memory_gb
        self.memory_cleanup_threshold = memory_cleanup_threshold
        self._batch_wait_time = batch_wait_time

    def get_batch_size(self) -> int:
        return self._batch_size

    def should_cleanup_memory(self, rss_mb: float) -> bool:
        # rss_mb 单位为MB，阈值为GB
        return rss_mb >= self.memory_cleanup_threshold * 1024

    def get_batch_wait_time(self) -> int:
        return self._batch_wait_time

def get_batch_config() -> BatchConfig:
    # 可根据实际需要自定义参数
    return BatchConfig()