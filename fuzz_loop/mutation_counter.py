class MutationCounter:
    _instance = None
    
    def __init__(self):
        self.count = 0
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    def increment(self):
        self.count += 1
        
    def get_count(self):
        return self.count
        
    def reset(self):
        self.count = 0