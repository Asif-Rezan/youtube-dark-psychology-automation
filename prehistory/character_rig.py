"""Reusable Pillow rig for original Somoy Jatri stick figures."""
import math

INK = '#211d19'

def character(draw, x, y, *, female=False, facing=0, stride=0, wave=None, scale=1, walk_phase=None, blink=False, islamic=True, basket=False, point=False, work=None, expression="calm"):
    """Draw an original stick figure with articulated elbows and knees."""
    if facing not in (-1, 0, 1) or scale <= 0:
        raise ValueError('Use a positive scale and a front (0), left (-1), or right (1) view.')
    direction = facing or 1
    facing = abs(facing)
    # The foot anchor stays fixed while the upper body bobs.
    bob = 0 if walk_phase is None else 2.6 * abs(math.sin(walk_phase))

    def points(coordinates):
        return [(round(x + px * scale * direction), round(y + py * scale)) for px, py in coordinates]

    def line(coordinates, width=4):
        draw.line(points(coordinates), fill=INK, width=round(width * scale), joint='curve')

    def shape(coordinates, color):
        draw.polygon(points(coordinates), fill=color)
        line([*coordinates, coordinates[0]], 3)

    def oval(box, color, width=3):
        (x0, y0), (x1, y1) = points(box)
        draw.ellipse((min(x0, x1), y0, max(x0, x1), y1),
                     fill=color, outline=INK if width else None, width=round(width * scale))

    robe = '#427875' if female else '#a3613c'
    if not islamic:
        robe = '#bf8e60' if female else '#a67749'
    if walk_phase is not None:
        stride = 32 * math.sin(walk_phase)
    for side in (-1, 1):
        swing = side * stride
        hip = side * (7 if facing else 15)
        heel = hip + swing
        lift = max(0, side * math.cos(walk_phase)) * 13 if walk_phase is not None else 0
        foot_y = -lift
        line([(hip, -91-bob), (hip + swing * .55, -42-lift*.5), (heel, foot_y),
              (heel + (12 * facing if facing else 10 * side), foot_y)])
    y -= bob * scale
    oval([(-9, -180), (9, -152)], 'white', 2)
    shape([(-23,-161),(-9,-167),(9,-167),(22,-159),(25,-123),(32,-80),
           (24,-76),(15,-82),(8,-73),(-2,-80),(-12,-74),(-18,-83),(-30,-77),(-26,-121)], robe)
    line([(-7,-156),(-10,-130),(-15,-105)], 2)

    for side in (-1, 1):
        shoulder = side * (12 if facing else 23)
        swing = -side * stride
        elbow = (shoulder + side * 15 + swing * .45, -132)
        hand = (shoulder + side * 17 + swing, -105)
        if basket:
            elbow = (shoulder + side * 8, -133)
            hand = (20 + side * 15, -129)
        elif work is not None:
            elbow = (shoulder + 28, -137 + 14*math.sin(work))
            hand = (48 + side*8, -117 + 22*math.sin(work))
        elif point and side == 1:
            elbow = (52, -163)
            hand = (91, -181)
        elif wave is not None and side == 1:
            elbow = (49, -150)
            angle = .35 + .48 * math.sin(wave)
            hand = (elbow[0] + 44 * math.sin(angle), elbow[1] - 44 * math.cos(angle))
        line([(shoulder, -158), elbow, hand])
        if point and side == 1:
            hx, hy = hand
            line([(hx-4,hy+1),(hx+9,hy-4)], 3)
        elif wave is not None and side == 1:
            hx, hy = hand
            shape([(hx-4,hy+3),(hx-7,hy-4),(hx-7,hy-8),(hx-3,hy-5),
                   (hx-4,hy-15),(hx,hy-15),(hx+2,hy-8),(hx+4,hy-13),
                   (hx+7,hy-11),(hx+7,hy-3),(hx+4,hy+3)], 'white')
        else:
            oval([(hand[0]-4,hand[1]-4),(hand[0]+4,hand[1]+4)], 'white', 2)

    if basket:
        shape([(0,-128),(40,-128),(34,-105),(6,-105)], '#ba874d')
        line([(3,-116),(37,-116)], 2)
        line([(9,-129),(10,-139),(20,-143),(30,-139),(31,-129)], 2)

    head_x = 9 * facing
    if female and islamic:
        shape([(head_x-43,-193),(head_x-44,-222),(head_x-34,-244),(head_x-15,-257),
               (head_x+12,-260),(head_x+34,-248),(head_x+43,-226),(head_x+41,-190),
               (head_x+29,-153),(head_x+4,-147),(head_x-30,-155)], '#335954')
    if female and not islamic:
        for side in (-1, 1):
            lock = [(33,-240),(44,-229),(48,-204),(45,-178),
                    (53,-158),(39,-166),(29,-162),(27,-190)]
            shape([(head_x + side * px, py) for px, py in lock], '#4a2c24')
    oval([(head_x-38,-247),(head_x+38,-173)], '#ffffff')
    if facing:
        shape([(head_x+33*facing,-221),(head_x+43*facing,-214),(head_x+33*facing,-211)], '#ffffff')
    if islamic and not female:
        shape([(head_x-36,-228),(head_x-36,-248),(head_x-23,-258),(head_x+18,-259),
               (head_x+35,-248),(head_x+36,-230),(head_x+15,-233),(head_x-12,-231)], '#e5d5af')
        line([(head_x-28,-240),(head_x-10,-245),(head_x+15,-244),(head_x+28,-240)], 2)
    if not islamic:
        hair = '#4a2c24' if female else '#493224'
        fringe = [(-39,-218),(-40,-239),(-29,-251),(-15,-258),(-21,-263),(-4,-260),
                  (8,-263),(26,-257),(39,-243),(36,-230),(23,-239),(13,-248),
                  (6,-236),(-3,-246),(-15,-231),(-22,-238),(-32,-225),(-38,-207)]
        if female:
            fringe = [(-41,-212),(-43,-235),(-34,-251),(-19,-260),(5,-262),
                      (25,-256),(40,-241),(40,-223),(26,-233),(11,-248),
                      (5,-253),(-6,-240),(-21,-233),(-33,-227),(-36,-207)]
        shape([(head_x + px, py) for px, py in fringe], hair)
    eyes = [head_x + 16*facing] if facing else [head_x-12, head_x+12]
    for eye in eyes:
        if blink:
            line([(eye-4,-218),(eye+4,-218)], 2)
        else:
            oval([(eye-3,-221),(eye+3,-215)], INK, 0)
    smile = head_x + 19 * facing
    if expression == 'surprised':
        oval([(smile-5,-205),(smile+5,-196)],INK,0)
    elif expression == 'curious':
        line([(smile-7,-198),(smile+6,-201)],2)
    else:
        line([(smile-6,-201),(smile,-198),(smile+6,-201)],2)
