from maya import cmds

import json
from pathlib import Path


with open(str(Path(__file__).parent / 'face_board.json'), 'r') as f:
    board_shape = json.loads(f.read())


def create_shape(name, shape, degree=1, global_scale=1.0):
    shape = [[value * global_scale for value in row] for row in shape]

    transform = cmds.curve(n=name, d=degree, p=shape)
    cmds.rename(
        cmds.listRelatives(transform, s=True, f=True), "{}Shape".format(transform)
    )
    return transform


def set_color(node, color):
    node_shape = cmds.listRelatives(node, s=True, f=True)[0]

    color_type = True if isinstance(color, list) else False

    cmds.setAttr(f'{node_shape}.overrideEnabled', 1)
    cmds.setAttr(f'{node_shape}.overrideRGBColors', color_type)
    if color_type:
        for a, b in zip(('R', 'G', 'B'), color):
            cmds.setAttr(f'{node_shape}.overrideColor{a}', b)
        return

    cmds.setAttr(f'{node_shape}.overrideColor', color)


def set_transformations(node, translation=None, rotation=None, scale=None, global_scale=1.0):
    if translation:
        cmds.xform(node, t=[value * global_scale for value in translation])
    if rotation:
        cmds.xform(node, ro=rotation)
    if scale:
        cmds.xform(node, s=[value * global_scale for value in scale])


def set_limits(node, txLimits=None, tyLimits=None):
    if txLimits:
        cmds.transformLimits(node, tx=txLimits)
        cmds.transformLimits(node, etx=(True, True))
    if tyLimits:
        cmds.transformLimits(node, ty=tyLimits)
        cmds.transformLimits(node, ety=(True, True))


def lock_n_hide(node, avoid):
    if not isinstance(avoid, list):
        avoid = [avoid]

    avoid_attributes = {
        "tx": ["tx", "translateX"],
        "translateX": ["tx", "translateX"],
        "ty": ["ty", "translateY"],
        "translateY": ["ty", "translateY"],
        "tz": ["tz", "translateZ"],
        "translateZ": ["tz", "translateZ"],
        "rx": ["rx", "rotateX"],
        "rotateX": ["rx", "rotateX"],
        "ry": ["ry", "rotateY"],
        "rotateY": ["ry", "rotateY"],
        "rz": ["rz", "rotateZ"],
        "rotateZ": ["rz", "rotateZ"],
        "sx": ["sx", "scaleX"],
        "scaleX": ["sx", "scaleX"],
        "sy": ["sy", "scaleY"],
        "scaleY": ["sy", "scaleY"],
        "sz": ["sz", "scaleZ"],
        "scaleZ": ["sz", "scaleZ"],
    }

    attributes = [
        "tx",
        "ty",
        "tz",
        "rx",
        "ry",
        "rz",
        "sx",
        "sy",
        "sz",
        "translateX",
        "translateY",
        "translateZ",
        "rotateX",
        "rotateY",
        "rotateZ",
        "scaleX",
        "scaleY",
        "scaleZ",
        "visibility",
    ]

    attrs_to_avoid = list()
    for attr in avoid:
        attrs_to_avoid.extend(
            item for item in avoid_attributes[attr] if item not in attrs_to_avoid
        )

    attributes = [item for item in attributes if item not in attrs_to_avoid]

    for attr in attributes:
        cmds.setAttr(f"{node}.{attr}", k=False, l=True, cb=False)


class FaceBoard:
    def __init__(self, global_scale=1.0):
        self.suffix = "ctrl"
        self.base_board = "FaceBoard"
        self.root_joint = "Root_Jnt_Exp"
        self.head_joint = "C_Head_DrivenJnt_Exp"
        self.face_joint = "bn_face_Exp"
        
        self.current_scale = global_scale
        self.controls = dict()

    def create_controls(self):
        base_board = create_shape(f"face_board_{self.suffix}", board_shape["outline_board_shape"], global_scale=self.current_scale)
        face_board = create_shape(f"face_board_{self.suffix}_crv", board_shape["face_board_shape"], 3, global_scale=self.current_scale)

        set_color(base_board, 17)
        cmds.setAttr(f"{face_board}.overrideEnabled", 1)
        cmds.setAttr(f"{face_board}.overrideDisplayType", 2)

        controls_group = list()
        for name, attr in board_shape["controls"].items():
            if not attr:
                continue

            scale = [1.0, 1.0, 1.0]
            ratio = 0.2
            if attr["shape"] == 0:
                scale = [2.0, 2.0, 2.0]
                ratio = 0.1

            transform = cmds.group(n=f"{name}_{self.suffix}_grp", em=True)
            outer_shape = create_shape(f"{name}_{self.suffix}_crv", board_shape["shapes"][str(attr["shape"])])
            inner_shape = cmds.circle(
                n=f"{name}_{self.suffix}", r=ratio, nr=(0, 0, 1), ch=False)[0]

            cmds.parent([outer_shape, inner_shape], transform)

            set_transformations(transform, attr["translate"], attr["rotate"], scale, global_scale=self.current_scale)
            set_limits(inner_shape, attr["txLimits"], attr["tyLimits"])
            lock_n_hide(inner_shape, attr["unlocked"])

            set_color(inner_shape, 17)
            cmds.setAttr(f"{outer_shape}.overrideEnabled", 1)
            cmds.setAttr(f"{outer_shape}.overrideDisplayType", 2)

            controls_group.append(transform)
            
            self.controls[inner_shape] = dict()
            if attr["txLimits"]:
                self.controls[inner_shape]['txLimits'] = attr["txLimits"]

            if attr["tyLimits"]:
                self.controls[inner_shape]['tyLimits'] = attr["tyLimits"]
        
        cmds.parent(controls_group + [face_board], base_board)

        root_group = cmds.group(base_board, n=self.base_board)

        if not cmds.objExists(self.head_joint):
            return

        offset = [value * self.current_scale for value in [20.0, 4.0, 0.0]]
        pos = cmds.xform(self.head_joint, q=True, ws=True, t=True)
        pos = [x + y for x, y in zip(pos, offset)]
        
        cmds.xform(root_group, ws=True, s=[0.6, 0.6, 0.6])
        cmds.xform(base_board, ws=True, t=pos)
        cmds.parentConstraint(self.head_joint, base_board, mo=True, weight=1)
