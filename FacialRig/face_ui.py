
from maya.api import OpenMaya, OpenMayaAnim
from maya import OpenMayaUI, cmds, mel

from .face_board import FaceBoard
from .blendshapes import BlendShape, BlendShapeData, get_blendshape
from .driven_keys import DrivenKeysData, load_driven_keys
from . import lib

import MayaData
# import Speedball

import math
import json

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
        self.body_skin = None
        self.body_skeleton = None
        self.teeth_skin = None
        self.masks = dict()

        self.global_scale = None

        self.anim_data = dict()
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
        head_layout = QtWidgets.QHBoxLayout()
        head_label = QtWidgets.QLabel('HEAD JOINT NAME')
        self.head_field = QtWidgets.QLineEdit('Head_jnt')
        self.head_field.setMinimumHeight(20)
        self.head_field.setFont(self.default_font)
        head_layout.addWidget(head_label)
        head_layout.addWidget(self.head_field)

        teeth_layout = QtWidgets.QHBoxLayout()
        teeth_label = QtWidgets.QLabel('TEETH MESH')
        self.teeth_field = QtWidgets.QLineEdit('Teeth_Base')
        self.teeth_field.setMinimumHeight(20)
        self.teeth_field.setFont(self.default_font)
        teeth_layout.addWidget(teeth_label)
        teeth_layout.addWidget(self.teeth_field)

        joints_layout = QtWidgets.QHBoxLayout()
        joints_label = QtWidgets.QLabel('NUMBER FACE JOINTS')
        self.n_joints = QtWidgets.QSpinBox()
        self.n_joints.setMinimumHeight(20)
        self.n_joints.setFont(self.default_font)
        self.n_joints.setValue(81)
        joints_layout.addWidget(joints_label)
        joints_layout.addWidget(self.n_joints)

        self.blendshapes_button = QtWidgets.QPushButton('CREATE RIG')
        self.blendshapes_button.setMinimumSize(150, 60)

        self.update_button = QtWidgets.QPushButton('UPDATE SELECTED')
        self.update_button.setMinimumSize(150, 60)

        self.buttons = QtWidgets.QVBoxLayout()
        self.buttons.addLayout(head_layout)
        self.buttons.addLayout(teeth_layout)
        self.buttons.addLayout(joints_layout)
        self.buttons.addWidget(self.blendshapes_button)
        self.buttons.addWidget(self.update_button)

    def main_layout(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.addStretch()

        main_layout.addLayout(self.masks_layout)
        main_layout.addLayout(self.blendshapes_layout)
        main_layout.addLayout(self.buttons)

    def create_connections(self):
        self.blendshapes_button.clicked.connect(self.create_blendshapes)
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
        self.body_skin = MayaData.data.skin.get(self.base_head)
        self.body_skeleton = MayaData.data.skeleton.get(list(self.body_skin['influences'].values())[0])
        if self.teeth_field.text():
            self.teeth_skin = MayaData.data.skin.get(self.teeth_field.text())

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
        pass

    def import_mask(self):
        if not self.base_head:
            print('The base head mesh is missing')
            return

        file_paths, selected_filter = QtWidgets.QFileDialog.getOpenFileNames(self.MAYA_DIALOG, 'Import Masks', '', self.FILE_FILTER)
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
        active_list = OpenMaya.MGlobal.getActiveSelectionList()

        if not self.base_head:
            print('The base head mesh is missing')
            return

        if active_list.isEmpty():
            print('Please select the target head mesh')
            return
        target_mesh = active_list.getDagPath(0)

        if not OpenMaya.MFnDagNode(target_mesh).typeName == 'transform':
            print('Please select a mesh type object')
            return
        try:
            target_mesh.extendToShape().hasFn(OpenMaya.MFn.kMesh)
        except RuntimeError:
            print('Please select a mesh type object')
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
        self.create_controls(target_mesh)

    def transfer_n_bake_animations(self, target_mesh):
        source_node = OpenMaya.MSelectionList().add(self.data.blend_node).getDependNode(0)
        source_node = OpenMaya.MFnDependencyNode(source_node)

        target_node = OpenMaya.MSelectionList().add(get_blendshape(target_mesh))
        target_node = OpenMaya.MFnDependencyNode(target_node.getDependNode(0))

        source_plug = source_node.findPlug('weight', False)
        target_plug = target_node.findPlug('weight', False)

        mod = OpenMaya.MDGModifier()
        for i in range(source_plug.numElements()):
            source_shape = source_plug.elementByPhysicalIndex(i)
            target_shape = target_plug.elementByPhysicalIndex(i)

            mod.connect(source_shape, target_shape)
        mod.doIt()

        # MayaData.skin.load(Speedball.Head.skin, target_mesh)
        joints = MayaData.skin.get_skin_joints(target_mesh)

        cmds.bakeResults([target_plug.name()] + joints, t=(0, self.current_frame), dic=True, pok=True, simulation=True)

    def key_control(self, node, attribute, neutral_value, target_value):

        lib.set_key(node, attribute, neutral_value, self.current_frame)
        self.current_frame += 1

        self.anim_data[self.current_frame] = {'node': node, 'attribute': attribute, 'value': target_value}
        lib.set_key(node, attribute, target_value, self.current_frame)
        self.current_frame += 1

        lib.set_key(node, attribute, neutral_value, self.current_frame)

    def create_controls(self, target_mesh):
        # TODO: Get skinned body from Base Head
        if not self.face_board:
            if not self.data:
                print('Couldn\'t find blendshapes')
                return

            self.face_board = FaceBoard(self.head_field.text(), self.global_scale.factor)

        if not self.base_head:
            print('A base blendshape head needs to be generated before applying it')
            return

        self.face_board.create_controls()

        # Temporarily add suffix to skeleton and copy it
        original_joints = [cmds.rename(jnt, jnt + '_temp') for jnt in self.body_skeleton['joints']]

        load_driven_keys(DrivenKeysData.POSES, self.global_scale.factor)
        return

        # Creates animation for each blendshape face control (excluding tongue)
        OpenMaya.MTime.setUIUnit(OpenMaya.MTime.kNTSCFrame)

        # TODO: Set Maya max frame duration
        start_frame = OpenMaya.MTime(self.current_frame, OpenMaya.MTime.uiUnit())
        OpenMayaAnim.MAnimControl.setAnimationStartTime(start_frame)
        OpenMayaAnim.MAnimControl.setMinTime(start_frame)
        OpenMayaAnim.MAnimControl.setCurrentTime(start_frame)

        excluded = ['fidget_ctrl', 'head_ctrl', 'lipSeal_ctrl', 'tongue_ctrl', 'tongue_curl_ctrl', 'tongue_forward_ctrl']

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

        for cor in self.data.correctives.values():
            first, second = [DrivenKeysData.SHAPES[each] for each in cor]
            first_ctr, first_attr = first[0].split('.')
            second_ctr, second_attr = second[0].split('.')

            lib.set_key(first_ctr, first_attr, 0, self.current_frame)
            lib.set_key(second_ctr, second_attr, 0, self.current_frame)

            self.current_frame += 1
            lib.set_key(first_ctr, first_attr, first[-1], self.current_frame)
            lib.set_key(second_ctr, second_attr, second[-1], self.current_frame)

            self.current_frame += 1
            lib.set_key(first_ctr, first_attr, 0, self.current_frame)
            lib.set_key(second_ctr, second_attr, 0, self.current_frame)

        # Apply blendshape masks and bake animations to it
        duplicated_mesh = self.data.duplicate_n_apply_masks()
        # MayaData.skin.load(Speedball.Head.skin, duplicated_mesh)
        # TODO: Make sure the eyes and tongue joints are placed correctly

        self.transfer_n_bake_animations(duplicated_mesh)

        # Load the mesh in the Houdini plugin and get the output
        output_skin = lib.run_dembones(duplicated_mesh, self.current_frame)
        output_jnt = 'joint0'

        # Delete temporarily created suffix and skeleton
        cmds.delete(self.face_board.root_joint)
        for jnt in original_joints:
            cmds.rename(jnt, '_'.join(jnt.split('_')[:-1]))

        if not cmds.objExists(output_jnt):
            print("No output joint was found")
            return

        facial_joints = cmds.listRelatives(output_jnt, ad=True)

        # Check what joints are being changed when a specific control is changed
        mod = OpenMaya.MDagModifier()
        for jnt in facial_joints:
            jnt_obj = OpenMaya.MSelectionList().add(jnt).getDependNode(0)
            for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']:
                attr_plug = OpenMaya.MFnTransform(jnt_obj).findPlug(attr, False)
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

                    difference = round(pose_value - neutral_value, 5)
                    if -1e-3 <= difference <= 1e-3:
                        continue
                    if frame not in self.anim_data:
                        continue

                    driver_data = self.anim_data[frame]

                    driver = f"{driver_data['node']}.{driver_data['attribute']}"
                    driven = f"{jnt}.{attr}"

                    if driver not in self.face_driven_keys:
                        self.face_driven_keys[driver] = dict()
                    if driver_data['value'] not in self.face_driven_keys[driver]:
                        self.face_driven_keys[driver][driver_data['value']] = dict()

                    self.face_driven_keys[driver][driver_data['value']].update({driven: difference})

                mod.deleteNode(attr_plug.source().node())
        mod.doIt()

        cmds.parent(facial_joints, self.face_board.face_joint)
        for ctr in self.face_board.controls.keys():
            lib.delete_all_keys(ctr)

        load_driven_keys(self.face_driven_keys, self.global_scale.factor)
        load_driven_keys(DrivenKeysData.JOINTS, self.global_scale.factor)

        MayaData.skin.load(output_skin, duplicated_mesh)

        # Merge the first mesh with the output one onto a copied mesh
        merged_skin = lib.merge_skin(self.base_head, duplicated_mesh, output_jnt)
        MayaData.skin.load(merged_skin, duplicated_mesh)

        # copy skin weights onto final mesh
        MayaData.skin.copy_skin(duplicated_mesh, target_mesh)

        [cmds.rename(jnt, f'face_{n}_Exp') for n, jnt in enumerate(facial_joints, 1)]

        cmds.setAttr(f'{self.base_head}.visibility', False)
        cmds.delete(duplicated_mesh, output_jnt)
        cmds.select(cl=True)

        for i in range(10):
            OpenMaya.MGlobal.displayInfo('--------------------')
        OpenMaya.MGlobal.displayInfo('--Process finished--')
