from maya.api import OpenMaya, OpenMayaAnim
from maya import OpenMayaUI, cmds, mel

from .face_board import FaceBoard
from .blendshapes import BlendShape, BlendShapeData, get_blendshape
from .driven_keys import DrivenKeysData, load_driven_keys
from . import lib

import MayaData
# import Speedball

import math
from PySide2 import QtWidgets, QtCore, QtGui
from shiboken2 import wrapInstance
from functools import partial


'''
Author: Lucas Esposito
'''


def maya_main_window():
    main_window_ptr = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)


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
    ui_instance = None

    @classmethod
    def show_ui(cls):
        if not cls.ui_instance:
            cls.ui_instance = FaceUI()

        if cls.ui_instance.isHidden():
            cls.ui_instance.show()
        else:
            cls.ui_instance.raise_()
            cls.ui_instance.activateWindow()

    def __init__(self, parent=maya_main_window()):
        super(FaceUI, self).__init__(parent)

        self.setWindowTitle("Face Rig")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

        self.data = None
        self.face_board = None
        self.base_head = None
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
            self.edit_mode = not self.edit_mode

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

        for mask in BlendShapeData.MASKS:
            item = QtWidgets.QListWidgetItem(mask)
            item.setFont(self.default_font)
            self.masks_widget.addItem(item)

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
        self.blendshapes_button = QtWidgets.QPushButton('CREATE RIG')
        self.blendshapes_button.setMinimumSize(150, 60)

        self.update_button = QtWidgets.QPushButton('UPDATE SELECTED')
        self.update_button.setMinimumSize(150, 60)

        self.buttons = QtWidgets.QVBoxLayout()
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
        self.masks_widget.itemSelectionChanged.connect(self.load_mask)

    @staticmethod
    def check_existence(button_widget):
        red = QtGui.QColor(255, 182, 193)
        green = QtGui.QColor(168, 216, 168)

        if cmds.objExists(button_widget.text()):
            button_widget.setStyleSheet(f"background-color: {green.name()}; color: black;")
            return

        button_widget.setStyleSheet(f"background-color: {red.name()}; color: black;")
        return button_widget.text()

    @staticmethod
    def check_vtx_count(main_mesh, button_widget):
        red = QtGui.QColor(255, 182, 193)

        main_mesh = OpenMaya.MSelectionList().add(main_mesh).getDagPath(0)
        sec_mesh = OpenMaya.MSelectionList().add(button_widget.text()).getDagPath(0)

        main_count = OpenMaya.MFnMesh(main_mesh).numVertices
        sec_count = OpenMaya.MFnMesh(sec_mesh).numVertices

        if main_count != sec_count:
            button_widget.setStyleSheet(f"background-color: {red.name()}; color: black;")
            return button_widget.text()

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

    # @staticmethod
    # def get_color_ramp_value(value):
    #     if value <= 0.4:
    #         # Linear interpolation between (0, 0, 255) and (0, 255, 0) for the range [0.0, 0.4]
    #         r = 0
    #         g = int(255 * (value / 0.4))
    #         b = int(255 - 255 * (value / 0.4))
    #     elif value <= 0.6:
    #         # Linear interpolation between (0, 255, 0) and (255, 255, 0) for the range [0.4, 0.6]
    #         r = int(255 * ((value - 0.4) / 0.2))
    #         g = 255
    #         b = int(255 - 255 * ((value - 0.4) / 0.2))
    #     elif value <= 0.8:
    #         # Linear interpolation between (255, 255, 0) and (255, 128, 0) for the range [0.6, 0.8]
    #         r = 255
    #         g = int(255 - 127 * ((value - 0.6) / 0.2))
    #         b = int(255 - 127 * ((value - 0.6) / 0.2))
    #     else:
    #         # Linear interpolation between (255, 128, 0) and (255, 0, 0) for the range [0.8, 1.0]
    #         r = 255
    #         g = int(128 - 128 * ((value - 0.8) / 0.2))
    #         b = 0
    #
    #     return r, g, b

    def toggle_mask_mode(self):
        if not self.base_head:
            return

        self.edit_mode = not self.edit_mode
        if not self.edit_mode:
            self.edit_mask_button.setStyleSheet("")
            return

        mel.eval('PaintVertexColorToolOptions;')

        green = QtGui.QColor(168, 216, 168)
        self.edit_mask_button.setStyleSheet(f"background-color: {green.name()}; color: black;")
        self.load_mask()

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

        color_array = OpenMaya.MColorArray()
        mesh_mfn = OpenMaya.MFnMesh(path)
        comp_mfn = OpenMaya.MFnSingleIndexedComponent(comp)
        selected_vertices = comp_mfn.getElements()

        [color_array.append(OpenMaya.MColor(vtx_color)) for i in selected_vertices]
        mesh_mfn.setVertexColors(color_array, selected_vertices)

        mask = self.masks_widget.currentItem()
        if mask.text() not in self.masks:
            self.masks[mask.text()] = dict()
        for vtx in selected_vertices:
            self.masks[mask.text()][vtx] = value

    def load_mask(self):
        base_head = OpenMaya.MSelectionList().add(self.base_head).getDagPath(0)
        mesh_mfn = OpenMaya.MFnMesh(base_head)
        try:
            color_set_name = mesh_mfn.currentColorSetName()
            mesh_mfn.deleteColorSet(color_set_name)
            mesh_mfn.createColorSet(color_set_name, True)
        except RuntimeError:
            pass

        mask = self.masks_widget.currentItem()
        if mask.text() not in self.masks:
            return

        color_array = OpenMaya.MColorArray()
        for color in list(self.masks[mask.text()].values()):
            color_array.append(OpenMaya.MColor(self.get_color_ramp(color)))

        mesh_mfn.setVertexColors(color_array, list(self.masks[mask.text()].keys()))

    def update_values_box(self, value):
        self.values_box.setValue(value / 100.0)

    def update_slider(self, value):
        self.slider.setValue(value * 100)

    def create_blendshapes(self):
        self.global_scale = SceneScale()
        active_list = OpenMaya.MGlobal.getActiveSelectionList()

        try:
            selection_list = OpenMaya.MSelectionList().add(BlendShapeData.BASE)
        except RuntimeError:
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

        base_head = selection_list.getDagPath(0)
        self.base_head = base_head.partialPathName()

        if not OpenMaya.MFnDagNode(base_head).typeName == 'transform':
            print('Please select a mesh type object')
            self.base_head = None
            return
        if not base_head.extendToShape().hasFn(OpenMaya.MFn.kMesh):
            print('Please select a mesh type object')
            self.base_head = None
            return

        missing_shapes = list()
        not_matching = list()
        for shape_row in range(self.blendshapes_layout.rowCount()):
            shape_widget = self.blendshapes_layout.itemAt(shape_row, QtWidgets.QFormLayout.FieldRole).widget()
            if not isinstance(shape_widget, QtWidgets.QPushButton):
                continue
            non_existent = self.check_existence(shape_widget)
            if non_existent:
                missing_shapes.append(non_existent)
                continue
            unmatched = self.check_vtx_count(self.base_head, shape_widget)
            if unmatched:
                not_matching.append(unmatched)

        if missing_shapes:
            print(f'The following shapes weren\'t found in the scene:')
            print(missing_shapes)
            return

        if not_matching:
            print(f'The following shapes don\'t match the vtx count:')
            print(not_matching)
            return

        self.data = BlendShape(self.base_head, self.global_scale.factor)
        self.data.create()
        # self.create_controls(target_mesh)

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

        if not self.face_board:
            if not self.data:
                print('Couldn\'t find blendshapes')
                return

            # MayaData.skeleton.load(Speedball.Head.Skeleton[self.selected_char[0]])
            # MayaData.skin.load(Speedball.Head.skin, self.base_head)
            # MayaData.skin.load(Speedball.Head.teeth_skin)

            self.face_board = FaceBoard(self.global_scale.factor)

        if not self.base_head:
            print('A base blendshape head needs to be generated before applying it')
            return

        self.face_board.create_controls()

        # Temporarily add suffix to skeleton and copy it
        original_joints = list()
        for jnt in cmds.listRelatives(self.face_board.root_joint, ad=True) + [self.face_board.root_joint]:
            if not cmds.objectType(jnt) == 'joint':
                continue
            original_joints.append(cmds.rename(jnt, jnt + '_temp'))
        # MayaData.skeleton.load(Speedball.Head.Skeleton[self.selected_char[0]])

        load_driven_keys(DrivenKeysData.POSES, self.global_scale.factor)

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
