from math import pi, sin, cos, radians, sqrt
from typing import Union, Iterable, Sequence, Callable, cast
from enum import Enum, auto
import cadquery as cq
from cadquery.hull import find_hull
from cadquery import (
    Edge,
    Face,
    Wire,
    Vector,
    Shape,
    Location,
    Vertex,
    Compound,
    Solid,
    Plane,
)
from cadquery.occ_impl.shapes import VectorLike, Real
import cq_warehouse.extensions
from build123d_common import *
from build_part import BuildPart


class BuildSketch:
    def __init__(self, mode: Mode = Mode.ADDITION):
        self.surface = Compound.makeCompound(())
        self.pending_edges: list[Edge] = []
        self.locations: list[Location] = [Location(Vector())]
        self.mode = mode

    def __enter__(self):
        context_stack.append(self)
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        context_stack.pop()
        if context_stack:
            if isinstance(context_stack[-1], Build3D):
                for edge in self.edge_list:
                    Build3D.add_to_context(edge, mode=self.mode)

    def edges(self) -> list[Edge]:
        return self.surface.Edges()

    def vertices(self) -> list[Vertex]:
        vertex_list = []
        for e in self.surface.Edges():
            vertex_list.extend(e.Vertices())
        return list(set(vertex_list))

    def consolidate_edges(self) -> Wire:
        return Wire.combine(self.pending_edges)[0]

    # def add(self, f: Face, mode: Mode = Mode.ADDITION):
    #     new_faces = self.place_face(f, mode)
    #     return new_faces if len(new_faces) > 1 else new_faces[0]

    @staticmethod
    def add_to_context(*objects: Union[Edge, Face], mode: Mode = Mode.ADDITION):
        if "context_stack" in globals() and mode != Mode.PRIVATE:
            if context_stack:  # Stack isn't empty
                new_faces = [obj for obj in objects if isinstance(obj, Face)]
                new_edges = [obj for obj in objects if isinstance(obj, Edge)]

                if mode == Mode.ADDITION:
                    context_stack[-1].surface = (
                        context_stack[-1].surface.fuse(*new_faces).clean()
                    )
                elif mode == Mode.SUBTRACTION:
                    context_stack[-1].surface = (
                        context_stack[-1].surface.cut(*new_faces).clean()
                    )
                elif mode == Mode.INTERSECTION:
                    context_stack[-1].surface = (
                        context_stack[-1].surface.intersect(*new_faces).clean()
                    )
                elif mode == Mode.CONSTRUCTION or mode == Mode.PRIVATE:
                    pass
                else:
                    raise ValueError(f"Invalid mode: {mode}")

                context_stack[-1].pending_edges.extend(new_edges)

    @staticmethod
    def get_context() -> "BuildSketch":
        return context_stack[-1]


class BuildFace:
    def __init__(self, *edges: Edge, mode: Mode = Mode.ADDITION):
        # pending_face = Face.makeFromWires(Build2D.get_context().consolidate_edges())
        pending_face = Face.makeFromWires(Wire.combine(edges)[0])
        BuildSketch.get_context().add_to_context(pending_face, mode)
        BuildSketch.get_context().pending_edges = []


class BuildHull:
    def __init__(self, *edges: Edge, mode: Mode = Mode.ADDITION):
        pending_face = find_hull(edges)
        BuildSketch.get_context().add_to_context(pending_face, mode)
        BuildSketch.get_context().pending_edges = []


class BuildWire(Wire):
    def __init__(self, *edges: Edge):
        wire = Wire.combine(edges)[0]
        super().__init__(wire.wrapped)


class PushPoints:
    def __init__(self, *pts: Union[VectorLike, Location]):
        new_locations = [
            Location(Vector(pt)) if not isinstance(pt, Location) else pt for pt in pts
        ]
        BuildSketch.get_context().locations = new_locations


class Rect(Compound):
    def __init__(
        self,
        width: float,
        height: float,
        angle: float = 0,
        mode: Mode = Mode.ADDITION,
    ):
        face = Face.makePlane(height, width).rotate(*z_axis, angle)
        new_faces = [
            face.moved(location) for location in BuildSketch.get_context().locations
        ]
        for face in new_faces:
            BuildSketch.add_to_context(face, mode=mode)
        BuildSketch.get_context().locations = [Location(Vector())]
        super().__init__(Compound.makeCompound(new_faces).wrapped)


class Circle(Compound):
    def __init__(
        self,
        radius: float,
        mode: Mode = Mode.ADDITION,
    ):
        face = Face.makeFromWires(Wire.makeCircle(radius, *z_axis))
        new_faces = [
            face.moved(location) for location in BuildSketch.get_context().locations
        ]
        for face in new_faces:
            BuildSketch.add_to_context(face, mode=mode)
        BuildSketch.get_context().locations = [Location(Vector())]
        super().__init__(Compound.makeCompound(new_faces).wrapped)


class Text(Compound):
    def __init__(
        self,
        txt: str,
        fontsize: float,
        font: str = "Arial",
        font_path: str = None,
        font_style: Font_Style = Font_Style.REGULAR,
        halign: Halign = Halign.LEFT,
        valign: Valign = Valign.CENTER,
        path: Union[Edge, Wire] = None,
        position_on_path: float = 0.0,
        angle: float = 0,
        mode: Mode = Mode.ADDITION,
    ) -> Compound:

        text_string = Compound.make2DText(
            txt,
            fontsize,
            font,
            font_path,
            Font_Style.legacy(font_style),
            Halign.legacy(halign),
            Valign.legacy(valign),
            position_on_path,
            path,
        ).rotate(Vector(), Vector(0, 0, 1), angle)
        new_compounds = [
            text_string.moved(location)
            for location in BuildSketch.get_context().locations
        ]
        new_faces = [face for compound in new_compounds for face in compound]
        for face in new_faces:
            BuildSketch.add_to_context(face, mode=mode)
        BuildSketch.get_context().locations = [Location(Vector())]
        super().__init__(Compound.makeCompound(new_faces).wrapped)
