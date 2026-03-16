"""
内存优化器
用于监控和优化程序内存使用
"""
import psutil
import gc
import os
import logging
from typing import Dict, List, Optional
import asyncio
import signal
import subprocess

logger = logging.getLogger(__name__)

class MemoryOptimizer:
    """内存优化器"""
    
    def __init__(self, max_memory_gb: float = 60.0):
        self.max_memory_gb = max_memory_gb
        self.max_memory_bytes = max_memory_gb * 1024 * 1024 * 1024
        self.process = psutil.Process()
        self.memory_history = []
        self.child_processes = []  # 跟踪子进程
        self.process_memory_threshold = 8000  # 子进程内存阈值(MB)
        
        logger.info(f"内存优化器初始化: 最大内存限制={max_memory_gb}GB")
    
    def get_memory_usage(self) -> Dict:
        """获取当前内存使用情况"""
        memory_info = self.process.memory_info()
        memory_percent = self.process.memory_percent()
        system_memory = psutil.virtual_memory()
        
        return {
            'rss_mb': memory_info.rss / 1024 / 1024,  # 实际使用内存(MB)
            'vms_mb': memory_info.vms / 1024 / 1024,  # 虚拟内存(MB)
            'memory_percent': memory_percent,
            'system_memory_percent': system_memory.percent,
            'system_available_gb': system_memory.available / 1024 / 1024 / 1024,
            'is_over_limit': memory_info.rss > self.max_memory_bytes
        }
    
    def check_memory_limit(self) -> bool:
        """检查是否超过内存限制"""
        usage = self.get_memory_usage()
        is_over = usage['is_over_limit']
        
        if is_over:
            logger.warning(f"内存使用超过限制: {usage['rss_mb']:.1f}MB > {self.max_memory_gb*1024:.1f}MB")
        
        return not is_over
    
    def force_garbage_collection(self):
        """强制垃圾回收"""
        before = self.get_memory_usage()
        gc.collect()
        after = self.get_memory_usage()
        
        freed_mb = before['rss_mb'] - after['rss_mb']
        if freed_mb > 0:
            logger.info(f"垃圾回收释放内存: {freed_mb:.1f}MB")
        
        return freed_mb
    
    def optimize_memory(self):
        """优化内存使用"""
        logger.info("开始内存优化...")
        
        # 1. 强制垃圾回收
        freed = self.force_garbage_collection()
        
        # 2. 记录当前状态
        usage = self.get_memory_usage()
        self.memory_history.append(usage)
        
        # 3. 保持历史记录在合理范围内
        if len(self.memory_history) > 100:
            self.memory_history = self.memory_history[-50:]
        
        logger.info(f"内存优化完成: 当前使用 {usage['rss_mb']:.1f}MB, 系统可用 {usage['system_available_gb']:.1f}GB")
        
        return usage
    
    def get_memory_recommendations(self) -> List[str]:
        """获取内存优化建议"""
        usage = self.get_memory_usage()
        recommendations = []
        
        if usage['rss_mb'] > self.max_memory_gb * 1024 * 0.75:
            recommendations.append("内存使用率超过80%，建议减少并发数")
        
        if usage['system_memory_percent'] > 75:
            recommendations.append("系统内存使用率超过90%，建议停止程序")
        
        if usage['system_available_gb'] < 20:
            recommendations.append("系统可用内存不足2GB，建议释放内存")
        
        return recommendations
    
    def should_stop_program(self) -> bool:
        """判断是否应该停止程序"""
        usage = self.get_memory_usage()
        
        # 只有在系统内存严重不足时才停止程序
        if (usage['system_memory_percent'] > 90 or 
            usage['system_available_gb'] < 0.5):
            return True
        
        return False
    
    def should_pause_new_tasks(self) -> bool:
        """判断是否应该暂停新任务创建"""
        usage = self.get_memory_usage()
        
        # 如果超过内存限制或系统内存不足
        if (usage['is_over_limit'] or 
            usage['system_memory_percent'] > 90 or 
            usage['system_available_gb'] < 2):
            return True
        
        return False
    
    def get_memory_cleanup_priority(self) -> str:
        """获取内存清理优先级"""
        usage = self.get_memory_usage()
        
        if usage['rss_mb'] > 8000:  # 超过8GB
            return "critical"
        elif usage['rss_mb'] > 6000:  # 超过6GB
            return "high"
        elif usage['rss_mb'] > 4000:  # 超过4GB
            return "medium"
        else:
            return "low"
    
    def register_child_process(self, process):
        """注册子进程"""
        self.child_processes.append(process)
        logger.debug(f"注册子进程: PID={process.pid}")
    
    def unregister_child_process(self, process):
        """注销子进程"""
        if process in self.child_processes:
            self.child_processes.remove(process)
            logger.debug(f"注销子进程: PID={process.pid}")
    
    def get_child_processes_memory(self) -> List[Dict]:
        """获取子进程内存使用情况"""
        child_memory = []
        for proc in self.child_processes[:]:  # 创建副本避免修改时出错
            try:
                if proc.poll() is None:  # 进程仍在运行
                    memory_info = proc.memory_info()
                    child_memory.append({
                        'pid': proc.pid,
                        'rss_mb': memory_info.rss / 1024 / 1024,
                        'vms_mb': memory_info.vms / 1024 / 1024,
                        'process': proc
                    })
                else:
                    # 进程已结束，从列表中移除
                    self.unregister_child_process(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # 进程不存在或无权限访问，从列表中移除
                self.unregister_child_process(proc)
        
        return child_memory
    
    def kill_high_memory_processes(self) -> int:
        """杀死占用内存较多的子进程"""
        child_memory = self.get_child_processes_memory()
        
        # 按内存使用量排序
        child_memory.sort(key=lambda x: x['rss_mb'], reverse=True)
        
        killed_count = 0
        for child in child_memory:
            if child['rss_mb'] > self.process_memory_threshold:
                try:
                    logger.warning(f"杀死高内存子进程: PID={child['pid']}, 内存={child['rss_mb']:.1f}MB")
                    child['process'].terminate()
                    child['process'].wait(timeout=5)  # 等待5秒
                    killed_count += 1
                    self.unregister_child_process(child['process'])
                except (psutil.NoSuchProcess, psutil.AccessDenied, subprocess.TimeoutExpired):
                    # 进程已结束或无法终止
                    self.unregister_child_process(child['process'])
                except Exception as e:
                    logger.error(f"杀死进程失败: {e}")
        
        if killed_count > 0:
            logger.info(f"已杀死 {killed_count} 个高内存子进程")
            # 强制垃圾回收
            self.force_garbage_collection()
        
        return killed_count
    
    def aggressive_memory_cleanup(self):
        """激进的内存清理"""
        logger.warning("开始激进内存清理...")
        
        # 记录清理前的内存使用
        before_usage = self.get_memory_usage()
        
        # 1. 杀死高内存子进程
        killed = self.kill_high_memory_processes()
        
        # 2. 强制垃圾回收
        freed = self.force_garbage_collection()
        
        # 3. 清理内存历史记录
        if len(self.memory_history) > 10:
            self.memory_history = self.memory_history[-5:]
        
        # 4. 清理Python内部缓存
        try:
            import sys
            # 清理模块缓存
            for module_name in list(sys.modules.keys()):
                if module_name.startswith('_') or module_name.startswith('test'):
                    del sys.modules[module_name]
        except Exception as e:
            logger.debug(f"清理模块缓存失败: {e}")
        
        # 5. 记录清理结果
        after_usage = self.get_memory_usage()
        total_freed = before_usage['rss_mb'] - after_usage['rss_mb']
        
        logger.info(f"激进清理完成: 杀死进程={killed}, 释放内存={total_freed:.1f}MB, "
                   f"当前内存={after_usage['rss_mb']:.1f}MB")
        
        return total_freed

# 全局内存优化器实例
memory_optimizer = MemoryOptimizer()

def get_memory_optimizer() -> MemoryOptimizer:
    """获取全局内存优化器实例"""
    return memory_optimizer

def check_memory_before_task() -> bool:
    """在执行任务前检查内存"""
    optimizer = get_memory_optimizer()
    
    if not optimizer.check_memory_limit():
        logger.error("内存使用超过限制，建议停止程序")
        return False
    
    if optimizer.should_stop_program():
        logger.error("系统内存不足，建议停止程序")
        return False
    
    return True

def optimize_memory_periodically():
    """定期优化内存"""
    optimizer = get_memory_optimizer()
    optimizer.optimize_memory()
    
    recommendations = optimizer.get_memory_recommendations()
    for rec in recommendations:
        logger.warning(rec)
