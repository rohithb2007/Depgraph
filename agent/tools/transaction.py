import os

class Transaction:
    def __init__(self):
        self._snapshots = {}
        self._committed = False
        self._rolled_back = False

    def snapshot(self, file_path: str) -> None:
        if self._committed or self._rolled_back:
            raise RuntimeError("Cannot snapshot: transaction is already committed or rolled back.")
            
        abs_path = os.path.normpath(os.path.abspath(file_path))
        
        # Only snapshot the FIRST time we touch the file in this transaction
        if abs_path not in self._snapshots:
            if not os.path.exists(abs_path):
                raise FileNotFoundError(f"Cannot snapshot {abs_path}: File does not exist.")
            with open(abs_path, "rb") as f:
                self._snapshots[abs_path] = f.read()

    def commit(self) -> None:
        if self._rolled_back:
            raise RuntimeError("Cannot commit: transaction already rolled back.")
        self._committed = True
        self._snapshots.clear()

    def rollback(self) -> None:
        if self._committed:
            raise RuntimeError("Cannot rollback: transaction already committed.")
        if self._rolled_back:
            return  # Idempotent
            
        for path, content in self._snapshots.items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)
                
        self._rolled_back = True
        self._snapshots.clear()
