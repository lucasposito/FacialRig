from maya.api import OpenMaya, OpenMayaAnim
from maya import OpenMayaUI, cmds, mel

from .face_board import FaceBoard
from .blendshapes import BlendShape, BlendShapeData
from .driven_keys import DrivenKeysData, load_driven_keys
from . import lib

import MayaData

import math
import json
import numpy

from pathlib import Path
from PySide2 import QtWidgets, QtCore, QtGui
from shiboken2 import wrapInstance
from functools import partial

'''
Author: Lucas Esposito
'''


def maya_main_window():
    maya_window = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(int(maya_window), QtWidgets.QWidget)


class SceneScale:
    unit_scale = {
        'mm': 10.0,
        'cm': 1.0,
        'm': 0.01,
        'km': 0.00001,
        'in': 0.393701,
        'ft': 0.0328084,
        'yd': 0.0109361}

    def __init__(self):
        self.factor = SceneScale.unit_scale[cmds.currentUnit(q=True, linear=True)]


class FaceUI(QtWidgets.QDialog):
    UI_INSTANCE = None
    COLOR_SET_NAME = 'FaceRigColorSet'
    FILE_FILTER = 'Json (*.json)'
    MAYA_DIALOG = QtWidgets.QDialog(maya_main_window())

    @classmethod
    def show_ui(cls):
        if not cls.UI_INSTANCE:
            cls.UI_INSTANCE = FaceUI()

        if cls.UI_INSTANCE.isHidden():
            cls.UI_INSTANCE.show()
        else:
            cls.UI_INSTANCE.raise_()
            cls.UI_INSTANCE.activateWindow()

    def __init__(self, parent=maya_main_window()):
        super(FaceUI, self).__init__(parent)

        self.setWindowTitle("Face Rig")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

        self.data = None
        self.face_board = None
        self.base_head = None
        self.head_skeleton = None
        self.head_skin = None
        self.teeth_skin = None
        self.masks = dict()

        self.global_scale = None

        self._rom_cache = list()

        self.anim_data = dict()
        self.comb_data = dict()
        self.face_driven_keys = dict()
        self.current_frame = 1
        self.edit_mode = False

        self.default_font = QtGui.QFont()
        self.default_font.setPointSize(14)

        self.set_masks_layout()
        self.set_shapes_layout()
        self.button_layout()

        self.main_layout()
        self.create_connections()

    def closeEvent(self, event):
        if self.edit_mode:
            self.edit_mask_button.setStyleSheet("")
            self.toggle_mask_mode()

    def set_masks_layout(self):
        self.masks_layout = QtWidgets.QVBoxLayout()
        load_layout = QtWidgets.QHBoxLayout()
        weights_layout = QtWidgets.QHBoxLayout()
        slider_layout = QtWidgets.QHBoxLayout()
        import_layout = QtWidgets.QHBoxLayout()

        self.masks_widget = QtWidgets.QListWidget()
        self.load_mesh_button = QtWidgets.QPushButton('LOAD BASE HEAD')
        self.edit_mask_button = QtWidgets.QPushButton('EDIT MODE')
        load_layout.addWidget(self.load_mesh_button)
        load_layout.addWidget(self.edit_mask_button)

        for value in [0.0, 0.25, 0.5, 0.75, 1.0]:
            button_widget = QtWidgets.QPushButton(str(value))
            weights_layout.addWidget(button_widget)
            button_widget.clicked.connect(partial(self.set_vtx_value, value))

        self.values_box = QtWidgets.QDoubleSpinBox()
        self.values_box.setMinimum(0)
        self.values_box.setMaximum(1)
        self.values_box.setSingleStep(0.01)  # Set the step for decimal values
        self.values_box.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)

        self.slider = QtWidgets.QSlider()
        self.slider.setOrientation(QtCore.Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setTickInterval(10)
        self.slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider.setMaximumWidth(150)

        self.values_box.valueChanged.connect(self.update_slider)
        self.slider.valueChanged.connect(self.update_values_box)

        self.flood_button = QtWidgets.QPushButton('FLOOD')
        slider_layout.addWidget(self.values_box)
        slider_layout.addWidget(self.slider)
        slider_layout.addWidget(self.flood_button)

        self.mirror_button = QtWidgets.QPushButton('MIRROR')
        self.import_button = QtWidgets.QPushButton('IMPORT')
        self.export_button = QtWidgets.QPushButton('EXPORT')
        import_layout.addWidget(self.import_button)
        import_layout.addWidget(self.export_button)

        masks_label = QtWidgets.QLabel('MASKS')
        masks_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignCenter)

        self.masks_layout.addWidget(masks_label)
        self.masks_layout.addWidget(self.masks_widget)

        for mask in sorted(BlendShapeData.MASKS):
            item = QtWidgets.QListWidgetItem(mask)
            item.setFont(self.default_font)
            self.masks_widget.addItem(item)

        self.masks_widget.setCurrentItem(self.masks_widget.item(0))

        self.masks_layout.addLayout(load_layout)
        self.masks_layout.addLayout(weights_layout)
        self.masks_layout.addLayout(slider_layout)
        self.masks_layout.addWidget(self.mirror_button)
        self.masks_layout.addLayout(import_layout)

    def set_shapes_layout(self):
        self.blendshapes_layout = QtWidgets.QVBoxLayout()
        self.shapes_widget = QtWidgets.QListWidget()
        self.corrective_widget = QtWidgets.QListWidget()

        shapes_label = QtWidgets.QLabel('SHAPES')
        shapes_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignCenter)

        correctives_label = QtWidgets.QLabel('CORRECTIVES')
        correctives_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignCenter)

        self.blendshapes_layout.addWidget(shapes_label)
        self.blendshapes_layout.addWidget(self.shapes_widget)
        self.blendshapes_layout.addWidget(correctives_label)
        self.blendshapes_layout.addWidget(self.corrective_widget)

        for shape in BlendShapeData.SHAPES:
            item = QtWidgets.QListWidgetItem(shape)
            item.setFont(self.default_font)
            self.shapes_widget.addItem(item)

        for corrective in BlendShapeData.CORRECTIVES:
            item = QtWidgets.QListWidgetItem(corrective)
            item.setFont(self.default_font)
            self.corrective_widget.addItem(item)

    def button_layout(self):
        self.buttons = QtWidgets.QVBoxLayout()

        fields = [[QtWidgets.QLabel('HEAD JOINT'), QtWidgets.QLineEdit('Head_jnt')],
                  [QtWidgets.QLabel('FACE JOINT'), QtWidgets.QLineEdit('Face_jnt')],
                  [QtWidgets.QLabel('RIGHT EYE JOINT'), QtWidgets.QLineEdit('Eye_R_jnt')],
                  [QtWidgets.QLabel('LEFT EYE JOINT'), QtWidgets.QLineEdit('Eye_L_jnt')],
                  [QtWidgets.QLabel('JAW JOINT'), QtWidgets.QLineEdit('Jaw_jnt')],
                  [QtWidgets.QLabel('TEETH MESH'), QtWidgets.QLineEdit('Teeth_Base')],
                  [QtWidgets.QLabel('NUMBER OF FACE JOINTS'), QtWidgets.QSpinBox()]]

        self.head_field, self.face_field, self.r_eye_field, self.l_eye_field, self.jaw_field, self.teeth_field, self.n_joints = [n[-1] for n in fields]

        for widgets in fields:
            if isinstance(widgets[-1], QtWidgets.QSpinBox):
                widgets[-1].setValue(81)
            base_layout = QtWidgets.QHBoxLayout()
            widgets[-1].setMinimumHeight(20)
            widgets[-1].setFont(self.default_font)
            base_layout.addWidget(widgets[0])
            base_layout.addWidget(widgets[-1])
            self.buttons.addLayout(base_layout)

        self.rig_button = QtWidgets.QPushButton('CREATE RIG')
        self.rig_button.setMinimumSize(150, 60)

        self.rom_button = QtWidgets.QPushButton('CREATE ROM')
        self.rom_button.setMinimumSize(150, 60)

        self.buttons.addWidget(self.rig_button)
        self.buttons.addWidget(self.rom_button)

    def main_layout(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.addStretch()

        main_layout.addLayout(self.masks_layout)
        main_layout.addLayout(self.blendshapes_layout)
        main_layout.addLayout(self.buttons)

    def create_connections(self):
        self.rig_button.clicked.connect(self.generate_rig)
        self.rom_button.clicked.connect(self.generate_rom)

        self.load_mesh_button.clicked.connect(self.set_base_head)
        self.edit_mask_button.clicked.connect(self.toggle_mask_mode)
        self.flood_button.clicked.connect(self.set_vtx_value)
        self.mirror_button.clicked.connect(self.mirror_mask)
        self.import_button.clicked.connect(self.import_mask)
        self.export_button.clicked.connect(self.export_mask)
        self.masks_widget.itemSelectionChanged.connect(self.load_mask)

    @staticmethod
    def highlight_item(list_item_widget, exists=True):
        red = QtGui.QColor(255, 182, 193)
        green = QtGui.QColor(168, 216, 168)
        black = QtGui.QColor(0, 0, 0)

        list_item_widget.setForeground(black)
        if not exists:
            list_item_widget.setBackground(red)
            return
        list_item_widget.setBackground(green)

    @staticmethod
    def check_existence(list_widget, base_head):
        missing_shapes = list()
        not_matching = list()
        for row in range(list_widget.count()):
            shape_item = list_widget.item(row)
            if not cmds.objExists(shape_item.text()):
                missing_shapes.append(shape_item.text())
                FaceUI.highlight_item(shape_item, False)
                continue
            FaceUI.highlight_item(shape_item)

            unmatched = FaceUI.check_vtx_count(base_head, shape_item)
            if unmatched:
                not_matching.append(unmatched)
        return missing_shapes, not_matching

    @staticmethod
    def check_vtx_count(main_mesh, list_widget):
        main_mesh = OpenMaya.MSelectionList().add(main_mesh).getDagPath(0)
        sec_mesh = OpenMaya.MSelectionList().add(list_widget.text()).getDagPath(0)

        main_count = OpenMaya.MFnMesh(main_mesh).numVertices
        sec_count = OpenMaya.MFnMesh(sec_mesh).numVertices

        if main_count != sec_count:
            FaceUI.highlight_item(list_widget, False)
            return list_widget.text()

    @staticmethod
    def lerp(start, end, t):
        return (1.0 - t) * start + t * end

    @staticmethod
    def get_color_ramp(value):
        if value <= 0.4:
            t = value / 0.4
            return 0.0, FaceUI.lerp(0.0, 1.0, t), FaceUI.lerp(1.0, 0.0, t)
        elif value <= 0.6:
            t = (value - 0.4) / 0.2
            return FaceUI.lerp(0.0, 1.0, t), 1.0, FaceUI.lerp(1.0, 0.0, t)
        elif value <= 0.8:
            t = (value - 0.6) / 0.2
            return 1.0, FaceUI.lerp(1.0, 0.5, t), FaceUI.lerp(1.0, 0.0, t)
        else:
            t = (value - 0.8) / 0.2
            return 1.0, FaceUI.lerp(0.5, 0.0, t), 0.0

    def generate_rom(self):
        self.create_blendshapes()
        self.create_controls(True)

    def generate_rig(self):
        self.create_blendshapes()
        self.create_controls()

    def toggle_mask_mode(self):
        if not self.base_head:
            return

        self.load_mask()
        self.edit_mode = not self.edit_mode

        sel_list = OpenMaya.MSelectionList().add(self.base_head)
        OpenMaya.MGlobal.setActiveSelectionList(sel_list, OpenMaya.MGlobal.kReplaceList)
        mel.eval('toggleShadeMode;')

        if not self.edit_mode:
            self.edit_mask_button.setStyleSheet("")
            return

        green = QtGui.QColor(168, 216, 168)
        self.edit_mask_button.setStyleSheet(f"background-color: {green.name()}; color: black;")

    def set_base_head(self):
        active_list = OpenMaya.MGlobal.getActiveSelectionList()

        if active_list.isEmpty():
            print('Please select the base head mesh')
            return
        base_head = active_list.getDagPath(0)

        if not OpenMaya.MFnDagNode(base_head).typeName == 'transform':
            print('Please select a mesh type object')
            return
        try:
            base_head.extendToShape().hasFn(OpenMaya.MFn.kMesh)
        except RuntimeError:
            print('Please select a mesh type object')
            return

        self.base_head = base_head.partialPathName()
        self.head_skin = MayaData.skin.get(self.base_head)
        self.head_skeleton = MayaData.skeleton.get(list(self.head_skin.keys())[0])
        if self.teeth_field.text():
            self.teeth_skin = MayaData.skin.get(self.teeth_field.text())

        self.edit_mode = False
        self.toggle_mask_mode()

    def set_vtx_value(self, value=None):
        if not self.base_head:
            return

        base_head = OpenMaya.MSelectionList().add(self.base_head).getDagPath(0)
        sel_list = OpenMaya.MGlobal.getActiveSelectionList()
        try:
            path, comp = sel_list.getComponent(0)
        except IndexError:
            return

        if not base_head == path:
            return

        if not comp.apiType() == OpenMaya.MFn.kMeshVertComponent:
            print('Please select only vertices')
            return

        if not value:
            value = self.values_box.value()

        vtx_color = self.get_color_ramp(value)

        mesh_mfn = OpenMaya.MFnMesh(path)
        comp_mfn = OpenMaya.MFnSingleIndexedComponent(comp)
        mask = self.masks_widget.currentItem()

        if mask.text() not in self.masks:
            self.masks[mask.text()] = dict()
            neutral_color = self.get_color_ramp(0)

            all_vertices = range(mesh_mfn.numVertices)
            no_color_array = OpenMaya.MColorArray([OpenMaya.MColor(neutral_color) for _ in all_vertices])

            mesh_mfn.setVertexColors(no_color_array, all_vertices)
            self.highlight_item(self.masks_widget.currentItem())

            for vtx in all_vertices:
                self.masks[mask.text()][vtx] = 0.0

        selected_vertices = comp_mfn.getElements()

        color_array = OpenMaya.MColorArray([OpenMaya.MColor(vtx_color) for _ in selected_vertices])
        mesh_mfn.setVertexColors(color_array, selected_vertices)

        for vtx in selected_vertices:
            self.masks[mask.text()][vtx] = value

    def load_mask(self):
        sel_list = OpenMaya.MSelectionList().add(self.base_head)
        mesh_mfn = OpenMaya.MFnMesh(sel_list.getDagPath(0))

        if self.COLOR_SET_NAME in mesh_mfn.getColorSetNames():
            mesh_mfn.deleteColorSet(self.COLOR_SET_NAME)

        if not self.edit_mode:
            return

        mesh_mfn.createColorSet(self.COLOR_SET_NAME, True)
        cmds.polyColorSet(self.base_head, cs=self.COLOR_SET_NAME, ccs=True)

        mask = self.masks_widget.currentItem()
        if mask.text() not in self.masks:
            return

        color_array = OpenMaya.MColorArray()
        for color in list(self.masks[mask.text()].values()):
            color_array.append(OpenMaya.MColor(self.get_color_ramp(color)))

        mesh_mfn.setVertexColors(color_array, list(map(int, self.masks[mask.text()].keys())))

    def mirror_mask(self):
        mesh_mfn = OpenMaya.MSelectionList().add(self.base_head).getDagPath(0)
        mesh_mfn = OpenMaya.MFnMesh(mesh_mfn)

        mask_items = [self.masks_widget.item(i) for i in range(self.masks_widget.count())]

        temp_node = cmds.createNode('closestPointOnMesh')
        cmds.connectAttr(f'{self.base_head}.worldMesh', f'{temp_node}.inMesh')

        for mask in BlendShapeData.MASKS:
            if mask not in self.masks:
                continue

            side = mask.split('_')
            if side[0] != 'l':
                continue

            new_values = dict(zip(range(mesh_mfn.numVertices), numpy.zeros(mesh_mfn.numVertices)))

            target = '_'.join(['r'] + side[1:])

            for vtx, value in self.masks[mask].items():
                vtx = int(vtx)

                vtx_position = list(mesh_mfn.getPoint(vtx, OpenMaya.MSpace.kWorld))[:-1]
                if value == 0.0:
                    continue

                vtx_position[0] *= -1

                cmds.setAttr(f'{temp_node}.inPosition', *vtx_position)
                closest = cmds.getAttr(f'{temp_node}.closestVertexIndex')

                new_values[closest] = value

            self.masks[target] = new_values
            mask_widget = [mask for mask in mask_items if target == mask.text()]
            if not mask_widget:
                continue
            self.highlight_item(mask_widget[0])
        cmds.delete(temp_node)

    def import_mask(self):
        if not self.base_head:
            print('The base head mesh is missing')
            return

        file_paths, selected_filter = QtWidgets.QFileDialog.getOpenFileNames(self.MAYA_DIALOG, 'Import Masks', '',
                                                                             self.FILE_FILTER)
        if not file_paths:
            return

        mask_items = [self.masks_widget.item(i) for i in range(self.masks_widget.count())]
        for file in file_paths:
            file = Path(file)
            mask = [mask for mask in mask_items if file.stem == mask.text()]
            if not mask:
                continue
            if file.stem in self.masks:
                del self.masks[file.stem]

            self.highlight_item(mask[0])

            with open(str(file), 'r') as f:
                self.masks[file.stem] = json.loads(f.read())

    def export_mask(self):
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self.MAYA_DIALOG, 'Export Masks', QtCore.QDir.homePath())
        if not dir_path:
            return

        for mask in self.masks:
            file_path = Path(dir_path) / f'{mask}.json'
            with open(file_path, 'w') as f:
                f.write(json.dumps(self.masks[mask], indent=4))

    def update_values_box(self, value):
        self.values_box.setValue(value / 100.0)

    def update_slider(self, value):
        self.slider.setValue(value * 100)

    def create_blendshapes(self):
        self.global_scale = SceneScale()
        # active_list = OpenMaya.MGlobal.getActiveSelectionList()

        if not self.base_head:
            print('The base head mesh is missing')
            return

        # Check if all masks have data
        missing_masks = list()
        for row in range(self.masks_widget.count()):
            mask_item = self.masks_widget.item(row)
            if mask_item.text() not in self.masks:
                missing_masks.append(mask_item.text())
                self.highlight_item(mask_item, False)
                continue
            self.highlight_item(mask_item)

        if missing_masks:
            print(f'The following masks don\'t contain any data:')
            print(missing_masks)
            return

        missing_shapes = list()
        not_matching = list()

        for shapes in [self.shapes_widget, self.corrective_widget]:
            a, b = self.check_existence(shapes, self.base_head)
            missing_shapes.extend(a)
            not_matching.extend(b)

        if missing_shapes:
            print(f'The following shapes weren\'t found in the scene:')
            print(missing_shapes)
            return

        if not_matching:
            print(f'The following shapes don\'t match the vtx count:')
            print(not_matching)
            return

        if self.edit_mode:
            self.toggle_mask_mode()

        self.data = BlendShape(self.base_head, self.masks, self.global_scale.factor)
        self.data.create()

    def create_curve_attributes(self):

        direction_map = {'tx': {'positive': 'east', 'negative': 'west'},
                         'ty': {'positive': 'north', 'negative': 'south'}}

        data = dict()

        for frame in range(self.current_frame + 1):
            if frame not in self.anim_data:
                continue

            driver_data = self.anim_data[frame]
            ctr_name = driver_data['node']
            attr = driver_data['attribute']

            value = driver_data['value']

            direction = 'positive' if value > 0.0 else 'negative'
            name = f"{ctr_name}_{direction_map[attr][direction]}"
            cmds.addAttr(self.face_field.text(), longName=name, attributeType='float', minValue=0.0, maxValue=1.0, k=True)

            driven = f"{self.face_field.text()}.{name}"
            data.setdefault(f'{ctr_name}.{attr}', {}).setdefault(value, {})[driven] = 1.0

        return data

    def create_comb_data(self):

        for frame, data in self.comb_data.items():
            cmds.addAttr(self.face_field.text(), ln=data['attribute'], at='float', dv=0.0, k=True)
            attr_plug = OpenMaya.MSelectionList().add(self.face_field.text()).getDependNode(0)
            attr_plug = OpenMaya.MFnTransform(attr_plug).findPlug(data['attribute'], False)

            mod = OpenMaya.MDGModifier()
            clamp_output = list()
            for each in data['nodes']:
                ctr, limit = each
                ctr_name, ctr_attr = ctr.split('.')

                ctr_node = OpenMaya.MSelectionList().add(ctr_name).getDependNode(0)
                ctr_plug = OpenMaya.MFnTransform(ctr_node).findPlug(ctr_attr, False)

                clamp_node = mod.createNode('clamp')
                clamp_mfn = OpenMaya.MFnDependencyNode(clamp_node)
                if limit < 0:
                    min_plug = clamp_mfn.findPlug('minR', False)
                    min_plug.setFloat(limit)
                else:
                    max_plug = clamp_mfn.findPlug('maxR', False)
                    max_plug.setFloat(limit)

                input_plug = clamp_mfn.findPlug('inputR', False)
                clamp_output.append(clamp_mfn.findPlug('outputR', False))

                mod.connect(ctr_plug, input_plug)

            multiply_node = mod.createNode('multiplyDivide')
            multiply_mfn = OpenMaya.MFnDependencyNode(multiply_node)
            plug_a = multiply_mfn.findPlug('input1X', False)
            plug_b = multiply_mfn.findPlug('input2X', False)
            multiply_output = multiply_mfn.findPlug('outputX', False)

            self._rom_cache.append(multiply_node)

            clamp_a, clamp_b = clamp_output
            mod.connect(clamp_a, plug_a)
            mod.connect(clamp_b, plug_b)
            mod.connect(multiply_output, attr_plug)
            mod.doIt()

    def key_control(self, node, attribute, neutral_value, target_value):

        lib.set_key(node, attribute, neutral_value, self.current_frame)
        self.current_frame += 1

        self.anim_data[self.current_frame] = {'node': node, 'attribute': attribute, 'value': target_value}
        lib.set_key(node, attribute, target_value, self.current_frame)
        self.current_frame += 1

        lib.set_key(node, attribute, neutral_value, self.current_frame)

    def create_rom(self):
        self.current_frame = 1
        self.anim_data = dict()
        self.comb_data = dict()
        # Creates animation for each blendshape face control (excluding tongue)
        OpenMaya.MTime.setUIUnit(OpenMaya.MTime.kNTSCFrame)

        # TODO: Set Maya max frame duration
        start_frame = OpenMaya.MTime(self.current_frame, OpenMaya.MTime.uiUnit())
        OpenMayaAnim.MAnimControl.setAnimationStartTime(start_frame)
        OpenMayaAnim.MAnimControl.setMinTime(start_frame)
        OpenMayaAnim.MAnimControl.setCurrentTime(start_frame)

        excluded = ['fidget_ctr', 'head_ctr', 'lipSeal_ctr', 'tongue_ctr', 'tongue_curl_ctr',
                    'tongue_forward_ctr']

        for ctr, limits in self.face_board.controls.items():
            if ctr in excluded:
                continue

            if 'txLimits' in limits:
                if limits['txLimits'][0] != 0.0:
                    neutral_value = cmds.getAttr(f'{ctr}.tx')

                    self.key_control(ctr, 'tx', neutral_value, limits['txLimits'][0])
                    self.key_control(ctr, 'tx', neutral_value, limits['txLimits'][1])

                else:
                    self.key_control(ctr, 'tx', limits['txLimits'][0], limits['txLimits'][1])

            if 'tyLimits' in limits:
                if limits['tyLimits'][0] != 0.0:
                    neutral_value = cmds.getAttr(f'{ctr}.ty')

                    self.key_control(ctr, 'ty', neutral_value, limits['tyLimits'][0])
                    self.key_control(ctr, 'ty', neutral_value, limits['tyLimits'][1])

                else:
                    self.key_control(ctr, 'ty', limits['tyLimits'][0], limits['tyLimits'][1])

        for cor_name, cor_shapes in self.data.correctives.items():
            first, second = [DrivenKeysData.SHAPES[each] for each in cor_shapes]
            first_ctr, first_attr = first[0].split('.')
            second_ctr, second_attr = second[0].split('.')

            lib.set_key(first_ctr, first_attr, 0, self.current_frame)
            lib.set_key(second_ctr, second_attr, 0, self.current_frame)

            self.current_frame += 1
            self.comb_data[self.current_frame] = {'nodes': [first, second], 'attribute': cor_name}

            lib.set_key(first_ctr, first_attr, first[-1], self.current_frame)
            lib.set_key(second_ctr, second_attr, second[-1], self.current_frame)

            self.current_frame += 1
            lib.set_key(first_ctr, first_attr, 0, self.current_frame)
            lib.set_key(second_ctr, second_attr, 0, self.current_frame)

    def clean_rom(self):
        cmds.delete([OpenMaya.MFnDependencyNode(i).name() for i in self._rom_cache])

        last_frame = max(self.anim_data.keys())
        last_shape = self.anim_data[last_frame]
        lib.set_key(last_shape['node'], last_shape['attribute'], 0, last_frame + 1)

        for frame, data in self.comb_data.items():
            first, second = data['nodes']
            first, _ = first
            second, _ = second

            first_ctr, first_attr = first.split('.')
            lib.set_key(first_ctr, first_attr, 0, frame)

            sec_ctr, sec_attr = second.split('.')
            lib.set_key(sec_ctr, sec_attr, 0, frame)

            lib.set_key(self.face_field.text(), data['attribute'], 0, frame - 1)
            lib.set_key(self.face_field.text(), data['attribute'], 1, frame)
            lib.set_key(self.face_field.text(), data['attribute'], 0, frame + 1)

        for ctr in self.face_board.controls.keys():
            [cmds.keyTangent(f'{ctr}.{attr}', edit=True, itt='linear', ott='linear') for attr in ['tx', 'ty']]

        cmds.bakeResults(self.face_field.text(), hi='below', t=(0, self.current_frame), sm=True, pok=True)
        for i in cmds.listRelatives(self.face_field.text(), ad=1) + [self.face_field.text()]:
            cmds.delete(i, sc=True)
        cmds.delete(self.face_board.base_board)

    def create_controls(self, keep_rom=False):
        if self.face_board:
            return

        if not self.data:
            print('Couldn\'t find blendshapes')
            return

        if not self.base_head:
            print('A base blendshape head needs to be generated before applying it')
            return

        joints_list = OpenMaya.MSelectionList().add(self.jaw_field.text())

        jaw_joint = OpenMaya.MFnTransform(joints_list.getDependNode(0))
        jaw_joints = [jaw_joint.child(index) for index in range(jaw_joint.childCount())]

        joints_list.add(self.face_field.text())
        face_joint = OpenMaya.MFnTransform(joints_list.getDependNode(1))
        facial_joints = [face_joint.child(index) for index in range(face_joint.childCount()) if face_joint.child(index) not in jaw_joints]

        # TODO: Find a way to load facial joints - Mediapipe?
        face_mesh = 'Face_Base'  # TODO: temporarily hard coded

        if self.teeth_skin:
            print('loading teeth skin')

        self.face_board = FaceBoard(self.head_field.text(), self.global_scale.factor)

        self.face_board.create_controls()

        load_driven_keys(DrivenKeysData.POSES, self.global_scale.factor)
        self.create_rom()

        # TODO: Work on editing the drivenkeys manually
        lib.run_dembones(self.base_head, face_mesh, self.current_frame)

        joints_anim_data = dict()
        curves_anim_data = self.create_curve_attributes()

        self.create_comb_data()

        # Check what joints are being changed when a specific control is changed
        mod = OpenMaya.MDagModifier()
        for jnt in facial_joints:
            jnt_mfn = OpenMaya.MFnTransform(jnt)
            for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']:
                attr_plug = jnt_mfn.findPlug(attr, False)
                anim_mfn = OpenMayaAnim.MFnAnimCurve()

                if not anim_mfn.hasObj(attr_plug.source().node()):
                    continue

                anim_mfn.setObject(attr_plug.source().node())
                neutral_value = attr_plug.asDouble()
                if attr in ['rx', 'ry', 'rz']:
                    neutral_value = math.degrees(neutral_value)

                for frame in range(self.current_frame):
                    m_frame = OpenMaya.MTime(frame, OpenMaya.MTime.uiUnit())
                    index = anim_mfn.find(m_frame)
                    if not index:
                        continue
                    pose_value = anim_mfn.value(index)
                    if attr in ['rx', 'ry', 'rz']:
                        pose_value = math.degrees(pose_value)
                    driven = f"{jnt_mfn.partialPathName()}.{attr}"

                    difference = round(pose_value - neutral_value, 5)
                    if -1e-3 <= difference <= 1e-3:
                        continue
                    if frame in self.anim_data:
                        driver_data = self.anim_data[frame]
                        driver = f"{driver_data['node']}.{driver_data['attribute']}"
                        value = driver_data['value']
                    elif frame in self.comb_data:
                        comb_attr = self.comb_data[frame]['attribute']

                        for i in self.comb_data[frame]['nodes']:
                            ctr, val = i
                            if ctr in joints_anim_data and \
                                    val in joints_anim_data[ctr] and \
                                    driven in joints_anim_data[ctr][val]:
                                difference -= joints_anim_data[ctr][val][driven]

                        driver = f"{self.face_field.text()}.{comb_attr}"
                        value = 1
                    else:
                        continue

                    if driver not in joints_anim_data:
                        joints_anim_data[driver] = dict()
                    if value not in joints_anim_data[driver]:
                        joints_anim_data[driver][value] = dict()

                    joints_anim_data[driver][value].update({driven: difference})

                mod.deleteNode(attr_plug.source().node())
        mod.doIt()

        for attr_key in set(joints_anim_data.keys()).union(curves_anim_data.keys()):
            self.face_driven_keys[attr_key] = dict()
            for inner_key in set(joints_anim_data.get(attr_key, {}).keys()).union(
                    curves_anim_data.get(attr_key, {}).keys()):
                joint_data = joints_anim_data.get(attr_key, {}).get(inner_key, {})
                curve_data = curves_anim_data.get(attr_key, {}).get(inner_key, {})
                self.face_driven_keys[attr_key][inner_key] = {**joint_data, **curve_data}

        load_driven_keys(self.face_driven_keys, self.global_scale.factor)
        load_driven_keys(DrivenKeysData.JOINTS, self.global_scale.factor)

        if keep_rom:
            self.clean_rom()
            return

        for ctr in list(self.face_board.controls.keys()) + [self.face_field.text()]:
            lib.delete_all_keys(ctr)

        # Merge the first mesh with the output one onto a copied mesh
        # merged_skin = lib.merge_skin(self.base_head, face_mesh, self.head_field.text())
        # MayaData.skin.load(merged_skin, face_mesh)

        cmds.select(cl=True)

        for i in range(10):
            OpenMaya.MGlobal.displayInfo('--------------------')
        OpenMaya.MGlobal.displayInfo('--Process finished--')
