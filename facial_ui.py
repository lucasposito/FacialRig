import sys
import os
import json
import logging

from maya import OpenMayaUI, cmds

from PySide2 import QtCore, QtUiTools, QtWidgets
from shiboken2 import wrapInstance

from .facialRig import FacialRig
from .mayaData import CONST

main_window = OpenMayaUI.MQtUtil.mainWindow()
if sys.version_info.major >= 3:
    main_window = wrapInstance(int(main_window), QtWidgets.QWidget)
else:
    main_window = wrapInstance(long(main_window), QtWidgets.QWidget)


class TextMessageLogger(logging.Handler):
    def __init__(self, parent):
        super(TextMessageLogger, self).__init__()
        self.widget = QtWidgets.QPlainTextEdit(parent)
        self.widget.setReadOnly(True)

    def emit(self, record):
        message = self.format(record)
        self.widget.appendPlainText(message)


class FacialRigUI(QtWidgets.QDialog):
    ui_instance = None

    @classmethod
    def show_ui(cls):
        if not cls.ui_instance:
            cls.ui_instance = FacialRigUI()

        if cls.ui_instance.isHidden():
            cls.ui_instance.show()
        else:
            cls.ui_instance.raise_()
            cls.ui_instance.activateWindow()

    def __init__(self, parent=main_window):
        super(FacialRigUI, self).__init__(parent)

        self.setFixedSize(680, 450)
        self.setWindowTitle("Facial Rig")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

        self.facialRig = FacialRig()
        self.chars_directory = QtCore.QDir('{}\\charsCache'.format(CONST.MAIN_PATH))
        self._dialog = None
        self.ui = None

        self.init_ui()
        self.create_connections()

        self._log_box = TextMessageLogger(self)
        self.set_logger()

    def init_ui(self):
        local_path = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
        local_path = QtCore.QFile("{}\\R_FacialRig\\R_FacialRig.ui".format(local_path))
        local_path.open(QtCore.QFile.ReadOnly)

        loader = QtUiTools.QUiLoader()
        self.ui = loader.load(local_path, parentWidget=self)
        self.ui.charDisplay.setFocusPolicy(QtCore.Qt.NoFocus)
        self._refresh_view()

        local_path.close()

    def create_connections(self):
        self.ui.readButton.clicked.connect(self._read_data)
        self.ui.reloadButton.clicked.connect(self._reload_data)
        self.ui.saveButton.clicked.connect(self._save_dialog)
        self.ui.loadButton.clicked.connect(self._load)
        self.ui.solveButton.clicked.connect(self._solve_rig)

    def _read_data(self):
        self.facialRig.read_data()

    def _reload_data(self):
        fbx_path = self.ui.fbxPath.text()
        if fbx_path and not os.path.exists(fbx_path):
            logging.debug('The Given FBX Path Doesn\'t Exist')
            return
        cmds.file(force=True, new=True)
        self.facialRig.build_data(target_rig=fbx_path)

    def _save(self, name):
        if not name:
            return
        file_path = '{}/{}'.format(self.chars_directory.path(), name) + '.json'
        if os.path.exists(file_path):
            result = QtWidgets.QMessageBox.question(self.ui, 'Save', '{} already exists. Do you want to replace it?'.format(name))
            if result != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        with open(file_path, 'w') as f:
            f.write(json.dumps(self.facialRig.rig, indent=4))
        logging.debug('{} successfully saved!'.format(name))
        self._dialog.close()
        self._refresh_view()

    def _save_dialog(self):
        if not self.facialRig.rig.items():
            return

        self._dialog = QtWidgets.QDialog(self.ui)
        self._dialog.setWindowTitle('Save Character As')
        self._dialog.setWindowFlags(self._dialog.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self._dialog.setMinimumWidth(300)

        line_edit = QtWidgets.QLineEdit()
        save_button = QtWidgets.QPushButton('SAVE')
        save_button.setMinimumHeight(35)
        cancel_button = QtWidgets.QPushButton('CANCEL')
        cancel_button.setMinimumHeight(35)

        line_layout = QtWidgets.QFormLayout()
        line_layout.addRow('NAME:', line_edit)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)

        main_layout = QtWidgets.QVBoxLayout(self._dialog)
        main_layout.addLayout(line_layout)
        main_layout.addLayout(button_layout)

        save_button.clicked.connect(lambda: self._save(line_edit.text()))
        cancel_button.clicked.connect(self._dialog.close)
        self._dialog.exec_()

    def _load(self):
        selected = self.ui.charDisplay.currentItem()
        if not selected:
            logging.debug('No Character Was Selected!')
            return

        file_path = '{}/{}'.format(self.chars_directory.path(), selected.text()) + '.json'
        fbx_path = self.ui.fbxPath.text()
        if fbx_path and not os.path.exists(fbx_path):
            logging.debug('The Given FBX Path Doesn\'t Exist')
            return

        cmds.file(force=True, new=True)
        with open(file_path, 'r') as f:
            self.facialRig.build_data(json.loads(f.read()), fbx_path)
            self._clear_selection()

    def _clear_selection(self):
        self.ui.charDisplay.clearSelection()
        self.ui.charDisplay.setCurrentItem(None)

    def _refresh_view(self):
        self.ui.charDisplay.clear()
        for f in self.chars_directory.entryList(['*.json']):
            item = QtWidgets.QListWidgetItem(f.split('.')[0])
            self.ui.charDisplay.addItem(item)

    def set_logger(self):
        self._log_box.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(self._log_box)
        logging.getLogger().setLevel(logging.DEBUG)
        self.ui.logLayout.addWidget(self._log_box.widget)

    def _solve_rig(self):
        self.facialRig.solve_rig()
