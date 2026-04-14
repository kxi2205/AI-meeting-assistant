"""
Global Singleton to manage the active Meeting Bot.
Ensures UI refresh can safely reconnect to a detached daemon thread without using session_state as the sole source of truth.
"""
import queue
import threading

class _BotManager:
    def __init__(self):
        self.bot_instance = None
        self.bot_thread = None
        self.status_queue = None
        self.result_queue = None
        
        # We store history so on reconnect, the UI knows what happened
        self.status_history = [] 
        
    def is_running(self):
        return self.bot_thread is not None and self.bot_thread.is_alive()
        
    def start_bot(self, run_func):
        self.status_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.status_history = []
        
        self.bot_thread = threading.Thread(target=run_func, daemon=True)
        self.bot_thread.start()
        
    def push_status(self, evt):
        self.status_history.append(evt)
        if self.status_queue:
            self.status_queue.put(evt)
            
    def get_missed_status_history(self):
        """When UI reconnects, it retrieves what happened prior."""
        return self.status_history
        
    def stop_bot(self):
        if self.bot_instance:
            self.bot_instance.stop()

# Instantiate the singleton at the module level
bot_manager = _BotManager()
