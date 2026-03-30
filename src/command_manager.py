from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class Command(ABC):
    """Abstract base class for all undoable commands."""
    
    @abstractmethod
    def execute(self) -> None:
        pass
        
    @abstractmethod
    def undo(self) -> None:
        pass

class CommandManager:
    """Manages the history of commands to provide undo/redo functionality."""
    
    def __init__(self, max_history: int = 100):
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._max_history = max_history

    def execute_command(self, command: Command) -> None:
        """Executes a command and adds it to the undo stack."""
        command.execute()
        self._undo_stack.append(command)
        
        # Limit history size
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
            
        # Clear redo stack when a new command is executed
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Undoes the last executed command. Returns True if successful."""
        if not self._undo_stack:
            return False
            
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        return True

    def redo(self) -> bool:
        """Redoes the last undone command. Returns True if successful."""
        if not self._redo_stack:
            return False
            
        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)
        return True

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0
        
    def clear(self) -> None:
        """Clears both undo and redo stacks."""
        self._undo_stack.clear()
        self._redo_stack.clear()
