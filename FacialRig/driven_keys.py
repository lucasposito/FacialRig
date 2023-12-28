from maya import cmds

import json
from pathlib import Path


with open(str(Path(__file__).parent / 'driven_keys.json'), 'r') as f:
    driven_keys = json.loads(f.read())

with open(str(Path(__file__).parent / 'driven_keys_joints.json'), 'r') as f:
    driven_keys_joints = json.loads(f.read())

def get():
    pass

def load_driven_keys(data, global_scale=1.0):

    for ctr, pose_data in data.items():
        if not pose_data:
            continue

        for pose, driven_list in pose_data.items():
            for driven, value in driven_list.items():

                node, attr = driven.split('.')
                if attr in ['tx', 'ty', 'tz']:
                    value *= global_scale

                current_value = cmds.getAttr(driven)

                cmds.setDrivenKeyframe(node, attribute=[attr], cd=ctr, dv=0, itt="spline", ott="spline")
                
                cmds.setAttr(driven, current_value + value)

                cmds.setDrivenKeyframe(node, attribute=[attr], cd=ctr, dv=int(pose), itt="spline", ott="spline")

                cmds.setAttr(driven, current_value)


class DrivenKeysData:
    POSES = driven_keys['poses']
    SHAPES = driven_keys['shapes']
    JOINTS = driven_keys_joints
