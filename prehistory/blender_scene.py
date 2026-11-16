"""Headless Blender entry point for prehistoric storybook shots."""
import json
import math
import os
from pathlib import Path
from random import Random

import bpy
from mathutils import Vector

shot = json.loads(os.environ['PREHISTORY_SHOT'])
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
rng = Random(97 + shot['index'])
count = shot['frames']
setting, prop = shot['setting'], shot['prop']


def material(name, color, roughness=.76):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    node = mat.node_tree.nodes.get('Principled BSDF')
    node.inputs['Base Color'].default_value = (*color, 1)
    node.inputs['Roughness'].default_value = roughness
    return mat


def assign(name, mat, scale=None):
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    if scale:
        obj.scale = scale
    return obj


def rock(name, pos, scale, mat, detail=2):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=detail, location=pos)
    obj = assign(name, mat, scale)
    obj.rotation_euler.z = rng.random()*math.tau
    return obj


def box(name, pos, scale, mat):
    bpy.ops.mesh.primitive_cube_add(size=2, location=pos)
    return assign(name,mat,scale)


def cylinder(name, a, b, radius, mat):
    delta = Vector(b)-Vector(a)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10,radius=radius,depth=delta.length,
                                      location=(Vector(a)+Vector(b))/2)
    obj = assign(name,mat)
    obj.rotation_euler = delta.to_track_quat('Z','Y').to_euler()
    return obj


def key(obj, prop, frame, value):
    setattr(obj,prop,value)
    obj.keyframe_insert(data_path=prop,frame=frame)


sand = material('Warm sandstone',(.64,.33,.105))
grass = material('Meadow',(.19,.38,.077))
ground = sand if setting in ('workshop','cave','journey') else grass
clay = material('Ochre boulders',(.46,.215,.087))
dark_stone = material('Volcanic stone',(.19,.16,.14))
flint = material('Blue gray flint',(.27,.38,.39),.39)
wood = material('Branches',(.28,.13,.05))
leaves = [material('Storybook leaves '+str(i),color) for i,color in enumerate(
    ((.13,.35,.083),(.24,.52,.105),(.43,.59,.12)))]
cloud = material('Clouds',(.82,.91,1))
trail = material('Trail',(.64,.40,.17))
box('Ground',(0,10,-.23),(42,43,.22),ground)
box('Work path',(0,8,-.014),(3.3,35,.014),trail)
for i in range(15):
    rock('Distant hills',(-33+i*4.7,22+rng.uniform(-2,8),0),
         (rng.uniform(3,7),5,rng.uniform(1,4)),leaves[i%3],2)
for i in range(65):
    x = rng.uniform(-15,15)
    y = rng.uniform(-1,19)
    if abs(x)<3.2 and y<7:
        continue
    size = rng.uniform(.08,.40)
    rock('Terrain detail',(x,y,size*.25),(size,size*.65,size*.6),
         clay if setting=='cave' or i%3==0 else leaves[i%3],1)

for i,(x,y) in enumerate(((-6,3),(5,5),(-8,10),(8,11),(-4,13),(3,14))):
    if setting=='cave':
        rock('Cave wall',(x*.63,y,2.4),(3,3,5),clay)
        continue
    height = 2.5+rng.random()*1.7
    cylinder('Tree trunk',(x,y,0),(x+.18,y,height),.15,wood)
    for j in range(4):
        rock('Tree canopy',(x+(j-1.5)*.43,y+j*.13,height+j%2*.28),
             (1,.8,.63),leaves[(i+j)%3])
if setting != 'cave':
    for x,z in ((-8,5),(0,6),(10,5.5)):
        for j in range(4):
            rock('Cloud puff',(x+j*.7,25,z+(j%2)*.23),(.85,.5,.28),cloud)

focus = Vector(shot['focus'])
x,y,z = focus
if prop == 'stone':
    rock('Work surface',(x,y,.38),(.73,.57,.49),clay)
    rock('Flint core',(x,y,.79),(.34,.23,.19),flint)
    for side in (-1,1):
        rock('Flake',(x+side*.43,y-.22,.83),(.14,.085,.041),flint,1)
    if shot['action']=='work':
        leader = shot['actors'][shot['lead']]
        hammer = rock('Hammerstone',(x,y,1.25),(.126,.10,.11),dark_stone)
        direction = leader['direction']
        unit = leader['height']/448
        for frame in range(1,count+1):
            elapsed = .24 if shot.get('cover') else (frame-1)/shot['fps']
            lift = math.sin(elapsed * math.tau/.68)
            position = (leader['x'] + 56*1.48*unit*direction,
                        leader['y']-.07,
                        .05 + (24+(117-22*lift)*1.48)*unit + .06)
            key(hammer,'location',frame,position)
elif prop == 'fire':
    glow = material('Ember',(.99,.29,.019))
    shader = glow.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Emission Color'].default_value = (1,.22,.01,1)
    shader.inputs['Emission Strength'].default_value = 1.8
    for i in range(9):
        a = i*math.tau/9
        rock('Fire ring',(x+.63*math.cos(a),y+.63*math.sin(a),.10),(.22,.16,.17),dark_stone)
    for i in range(5):
        flame = rock('Flame',(x+rng.uniform(-.3,.3),y+rng.uniform(-.23,.23),.42),
                     (.15,.16,.42),glow)
        for frame in range(1,count+5,4):
            key(flame,'scale',frame,(.15,.16,rng.uniform(.33,.66)))
    bpy.ops.object.light_add(type='POINT',location=(x,y,.8))
    bpy.context.object.data.energy = 115
    bpy.context.object.data.color = (1,.30,.055)
elif prop == 'shelter':
    for side in (-1,1):
        cylinder('Shelter pole',(x+side*1.15,y-.65,0),(x,y-.65,2.24),.065,wood)
        cylinder('Shelter pole',(x+side*1.15,y+1.2,0),(x,y+1.2,2.24),.065,wood)
        roof = box('Hide cover',(x+side*.55,y+.30,1.15),(1.23,1.12,.07),clay)
        roof.rotation_euler.y = side*1.08
elif prop == 'food':
    rock('Gathering slab',(x,y,.28),(.79,.50,.31),clay)
    berry = material('Wild berries',(.68,.037,.115))
    for i in range(16):
        rock('Wild fruit',(x+rng.uniform(-.53,.53),y+rng.uniform(-.30,.23),.55),
             (.083,.079,.071),berry)
elif prop == 'map':
    hide = material('Hide map',(.78,.51,.24))
    box('Landscape map',(x,y,.32),(1.28,.85,.045),hide)
    path_mat = material('Map route',(.45,.08,.029))
    route = [(x-1+j*.33,y+.25*math.sin(j*.8),.39) for j in range(7)]
    for a,b in zip(route,route[1:]):
        cylinder('Route marking',a,b,.025,path_mat)
    for j in (0,3,6):
        rock('Route marker',route[j],(.085,.085,.065),flint,1)
else:
    box('Marked stone',(x,y,1.02),(1.12,.16,.83),clay)
    for i in range(5):
        points = [(x-.91+j*.39,y-.18,.75+i*.12+.13*math.sin(j+i)) for j in range(5)]
        for a,b in zip(points,points[1:]):
            cylinder('Inscribed line',a,b,.016,dark_stone)

for actor in shot['actors']:
    source = Path(actor['texture'])
    image = bpy.data.images.load(str(source))
    if not shot.get('cover'):
        image.source = 'SEQUENCE'
    mat = bpy.data.materials.new('Original character artwork')
    mat.use_nodes = True
    mat.surface_render_method = 'DITHERED'
    tree = mat.node_tree
    tree.nodes.clear()
    texture = tree.nodes.new('ShaderNodeTexImage')
    texture.image = image
    texture.image_user.frame_start = 1
    texture.image_user.frame_duration = count
    texture.image_user.use_auto_refresh = True
    emission = tree.nodes.new('ShaderNodeEmission')
    transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
    mix = tree.nodes.new('ShaderNodeMixShader')
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    tree.links.new(texture.outputs['Color'],emission.inputs['Color'])
    tree.links.new(texture.outputs['Alpha'],mix.inputs[0])
    tree.links.new(transparent.outputs[0],mix.inputs[1])
    tree.links.new(emission.outputs[0],mix.inputs[2])
    tree.links.new(mix.outputs[0],output.inputs[0])
    height = actor['height']
    width = height*384/448
    bpy.ops.mesh.primitive_plane_add(size=2,location=(actor['x'],actor['y'],height/2),
                                     rotation=(math.pi/2,0,0))
    subject = assign(actor['name'],mat,(width/2,height/2,1))
    # The rig's foot baseline sits just above the bottom edge of its texture.
    subject.location.z += .05
    if actor['action'] in ('walk','carry','gather'):
        end = actor['x']+actor['direction']*(1.35 if actor['action'] in ('walk','carry') else .38)
        key(subject,'location',1,subject.location.copy())
        stop = min(count, 1 + round(shot['fps']*2.05))
        if stop > 1:
            travel = (stop-1)/(shot['fps']*2.05)
            key(subject,'location',stop,(actor['x']+(end-actor['x'])*travel,
                                         actor['y']+.18*travel,subject.location.z))

scene.world = bpy.data.worlds.new('Warm storybook sky')
scene.world.use_nodes = True
bg = scene.world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = ((.15,.22,.42,1) if prop=='fire' else (.18,.61,1,1))
bg.inputs['Strength'].default_value = .8
bpy.ops.object.light_add(type='SUN',location=(-5,-5,9))
sun = bpy.context.object
sun.rotation_euler = (.52,-.64,-.48)
sun.data.energy = 1.25 if prop=='fire' else 2.0
sun.data.color = (1,.90,.71)
sun.data.angle = .15
bpy.ops.object.light_add(type='AREA',location=(1,-5,5))
fill = bpy.context.object
fill.rotation_euler = (Vector((0,0,1))-fill.location).to_track_quat('-Z','Y').to_euler()
fill.data.energy, fill.data.size = 430, 7

bpy.ops.object.camera_add()
camera = bpy.context.object
scene.camera = camera
framing = shot['framing']
if shot.get('cover'):
    framing = 'wide'
if framing == 'detail':
    position, target, lens = (x+.68,-5.05,2.1),(x-.21,y,1.25),43
elif framing == 'medium':
    position, target, lens = (x*.36+1.35,-6.45,2.25),(x*.65,.7,1.3),40
else:
    position, target, lens = (1.3,-9,2.9),(0,1,1.46),37
for frame, offset in ((1,0),(max(2,count),1)):
    location = Vector(position)+Vector((-.43*offset,.50*offset,0))
    camera.data.lens = lens
    key(camera,'location',frame,location)
    key(camera,'rotation_euler',frame,(Vector(target)-location).to_track_quat('-Z','Y').to_euler())

scene.render.engine = os.environ.get('PREHISTORY_ENGINE','CYCLES')
if scene.render.engine=='CYCLES':
    scene.cycles.samples = 6 if shot.get('cover') else 3
    scene.cycles.max_bounces = 4
    scene.cycles.transparent_max_bounces = 8
    scene.cycles.use_denoising = True
else:
    scene.eevee.taa_render_samples = 24
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.render.resolution_x,scene.render.resolution_y=shot['size']
scene.render.fps = shot['fps']
scene.frame_start,scene.frame_end=1,count
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.filepath = shot['output']
scene.frame_set(1)
bpy.ops.render.render(write_still=True) if shot.get('cover') else bpy.ops.render.render(animation=True)
