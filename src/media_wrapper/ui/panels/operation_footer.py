"""Shared, collapsible operation output below the workspace."""
from PySide6.QtWidgets import QCheckBox, QFrame, QSizePolicy, QTextEdit, QVBoxLayout


class OperationFooter(QFrame):
    def __init__(self, output: QTextEdit) -> None:
        super().__init__()
        self.setObjectName('operationFooter')
        self.setProperty('role', 'workspacePanel')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)
        self.toggle = QCheckBox('Operation')
        self.toggle.setProperty('role', 'disclosure')
        self.toggle.setAccessibleName('Show operation feedback')
        layout.addWidget(self.toggle)
        output.setProperty('role', 'console')
        output.setFixedHeight(120)
        layout.addWidget(output)
        output.hide()
        self.toggle.toggled.connect(output.setVisible)
