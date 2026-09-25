from copy import deepcopy
from enum import StrEnum
from itertools import product
from math import ceil
from os import listdir
from typing import Any, Generator, cast

from litemapy import BlockState, Entity, Region, Schematic, TileEntity
from nbtlib.tag import Double, Int, List

SEP: str = "//"


def offset_entities(
    entities: list[Entity], offset: tuple[int, int, int], append_to: list[Entity]
) -> None:
    """Copies entities from the `entities` list, offsets them by `offset` and appends to `append_to`."""
    dx, dy, dz = offset
    for entity in entities:
        new_entity = deepcopy(entity)
        x, y, z = entity._position
        new_entity._position = (x + dx, y + dy, z + dz)
        new_entity._data["Pos"] = List[Double](list(map(Double, new_entity._position)))
        append_to.append(new_entity)


def offset_tile_entities(
    tile_entities: list[TileEntity],
    offset: tuple[int, int, int],
    append_to: list[TileEntity],
) -> None:
    """Copies tile entities from the `tile_entities` list,
    offsets them by `offset` and appends to `append_to`."""
    dx, dy, dz = offset
    for tile_entity in tile_entities:
        new = deepcopy(tile_entity)
        x, y, z = tile_entity._position
        new._position = (x + dx, y + dy, z + dz)
        new._data["x"] = Int(x + dx)
        new._data["y"] = Int(y + dy)
        new._data["z"] = Int(z + dz)
        append_to.append(new)


def paste_region(
    reg1: Region,
    reg2: Region,
    offset: tuple[int, int, int] = (0, 0, 0),
    strict: bool = True,
) -> None:
    """Copies all blocks of region `reg2` into `reg1`, translating all block positions by `offset`."""
    for x, y, z in reg2.block_positions():  # type: ignore
        x_, y_, z_ = x + offset[0], y + offset[1], z + offset[2]
        # we normalize the origin to be at the corner with minimal coordinates
        if reg2.width < 0:
            x_ -= reg2.width + 1
        if reg2.height < 0:
            y_ -= reg2.height + 1
        if reg2.length < 0:
            z_ -= reg2.length + 1

        if not strict and (
            not 0 <= x_ < abs(reg1.width)
            or not 0 <= y_ < abs(reg1.height)
            or not 0 <= z_ < abs(reg1.length)
        ):
            continue
        reg1[x_, y_, z_] = reg2[x, y, z]

    offset_entities(reg2.entities, offset, reg1.entities)
    offset_tile_entities(reg2.tile_entities, offset, reg1.tile_entities)


def normalize_region(reg: Region) -> Region:
    new_reg = Region(
        reg.min_schem_x(),  # type: ignore
        reg.min_schem_y(),  # type: ignore
        reg.min_schem_z(),  # type: ignore
        abs(reg.width),
        abs(reg.height),
        abs(reg.length),
    )
    paste_region(new_reg, reg)
    return new_reg


def make_rectangle_contour(
    reg: Region, y: int, x0: int, z0: int, x1: int, z1: int, block: BlockState
) -> None:
    """Assuming that x0 <= x1 and z0 <= z1, makes a rectangular countour.
    Lower left corner: (x0, z0); upper right corner: (x1, z1)."""
    for x in range(x0, x1 + 1):
        reg[x, y, z0] = block
        reg[x, y, z1] = block
    for z in range(z0, z1 + 1):
        reg[x0, y, z] = block
        reg[x1, y, z] = block


def knapsack_solver(numbers: list[int], n: int) -> tuple[int, ...]:
    """Given a list of positive integers of size `m` sorted in descending order,
    and a natural number `n`, finds `m` positive integers `c[0], c[1], ...`
    such that `c[0] numbers[0] + c[1] numbers[1] + ... >= n` and this sum is minimal."""
    assert all(
        a > b > 0 for a, b in zip(numbers, numbers[1:])
    ), "Numbers are not in strictly descending order or not positive"
    # assert numbers[0] * len(numbers) <= n, "Out of scope of the solver"
    # first guess
    c = [0] * len(numbers)
    c[0] = ceil(n / numbers[0])
    best_ans = tuple([n - c[0] * numbers[0]] + c)
    if best_ans[0] == 0:
        return best_ans[1:]
    # knapsack is a co-NP-complete problem so don't judge me
    for coefs in product(range(numbers[0]), repeat=len(numbers) - 1):
        c = [0] + list(coefs)
        r = n - sum(ci * xi for ci, xi in zip(c, numbers))
        if r < 0:
            continue
        c[0] = ceil(r / numbers[0])
        remainder = -(r % numbers[0])
        if remainder < 0:
            remainder += numbers[0]
        best_ans = max(best_ans, tuple([-remainder] + c))

    return best_ans[1:]


class XDependence(StrEnum):
    NONE = "0"
    OFFSET = "1"
    TILE = "t"
    CAP = "c"


class TilingUnit:
    def __init__(self, name: str, region: Region):
        self.region: Region = normalize_region(region)
        self.group: str = "Unnamed"
        self.subgroup: str | None = None
        self.custom_id: str | None = None
        self.x_dependence: XDependence = XDependence.NONE
        self.depends_on_z: bool = False
        self.is_outline: bool = False
        self._parse_region_name(name)

    def _parse_region_name(self, name: str):
        """Assumes the following naming convention:

        `[group](str) // [name](str) or [subgroup](str)::[name](str) //
        [depends_on_W](0,1,t,c) // [depends_on_L](0,1) // [is_outline](0,1)`
        """
        args = name.split(SEP) + [None] * 5
        self.group = args[0].strip()  # type: ignore

        if args[1]:
            arg = args[1].strip()
            if "::" in arg:
                subgroup, custom_id = arg.split("::", maxsplit=1)
                self.subgroup = subgroup.strip()
                self.custom_id = custom_id.strip()
            else:
                self.custom_id = arg

        if args[2]:
            self.x_dependence = XDependence(args[2])

        if args[3]:
            self.depends_on_z = bool(int(args[3].strip()))

        if args[4]:
            self.is_outline = bool(int(args[4].strip()))

    def min_x(self) -> int:
        return self.region.min_schem_x()  # type: ignore

    def max_x(self) -> int:
        return self.region.max_schem_x()  # type: ignore

    def min_y(self) -> int:
        return self.region.min_schem_y()  # type: ignore

    def max_y(self) -> int:
        return self.region.max_schem_y()  # type: ignore

    def min_z(self) -> int:
        return self.region.min_schem_z()  # type: ignore

    def max_z(self) -> int:
        return self.region.max_schem_z()  # type: ignore


class TilingSubgroup:
    def __init__(self, name: str):
        self.name: str = name
        self.units: list[TilingUnit] = []
        self._knapsack_cache: tuple[int, ...] = ()

    @property
    def is_outline(self) -> bool:
        return self.units[0].is_outline

    @property
    def depends_on_z(self) -> bool:
        if self.is_outline:
            raise NotImplementedError(
                "The `.depends_on_z` property isn't defined for outline-generators."
            )
        return self.units[0].depends_on_z

    def verify(self, parent_name: str) -> None:
        sg_id = f"{parent_name}{SEP}{self.name}"
        cap_count = 0
        zdep_count = 0
        outline_count = 0

        for unit in self.units:
            if unit.x_dependence is XDependence.CAP:
                cap_count += 1
            zdep_count += unit.depends_on_z
            if not unit.is_outline:
                assert (
                    unit.x_dependence is not XDependence.OFFSET
                ), "'OFFSET' X-dependence is not supported yet"
                continue

            raise RuntimeError("Outline generators are not supported yet.")
            outline_count += unit.is_outline

            if unit.region.volume() > 1:  # type: ignore
                raise ValueError(
                    f"Subgroup '{sg_id}' has been recognized as an outline generator."
                    " Outline corners must be regions of size 1x1x1, not"
                    f" {unit.region.width}x{unit.region.height}x{unit.region.length}."
                )
            if unit.x_dependence not in (XDependence.NONE, XDependence.OFFSET):
                raise ValueError(
                    f"Subgroup '{sg_id}' has been recognized as an outline generator."
                    " Outline corners can not be flagged as caps or tiles."
                )

        if outline_count == 0:
            if cap_count > 1:
                raise ValueError(f"Subgroup '{sg_id}' has more than one cap-tile.")
            if zdep_count not in (0, len(self.units)):
                raise ValueError(
                    f"Subgroup '{sg_id}' has mixed Z-dependence, even though it's not an outline generator."
                )
        elif outline_count != 2 or len(self.units) != 2:
            raise ValueError(
                f"The outline-generating subgroup '{sg_id}' must have exactly 2 elements."
            )

    def get_box(self, width: int) -> tuple[int, int, int, int, int, int]:
        """Assuming that `.verify()` has been called,
        computes the minimal hitbox to enclose the tiled contraption.
        """
        if self.is_outline:
            raise RuntimeError(
                "The `.get_box()` method is poorly defined for outlines."
            )

        tiles: list[TilingUnit] = []
        cap = None
        for unit in self.units:
            if unit.x_dependence is XDependence.TILE:
                tiles.append(unit)
            elif unit.x_dependence is XDependence.CAP:
                cap = unit
        tiles.sort(key=lambda u: u.region.width, reverse=True)
        # Given tiles, we want to know their min_x - that's the starting point for tiling them;
        # The tiling continues until it exceeds schem_x = width - cap.width, i.e. we run
        # knapsack_solver(..., n = width - cap.width - min_x)
        cap_w = cap.region.width if cap else 0
        if tiles:
            t_min_x = min(u.min_x() for u in tiles)
            widths = [u.region.width for u in tiles]
            sol = knapsack_solver(widths, width - cap_w - t_min_x)
            self._knapsack_cache = sol
            t_max_x = t_min_x + sum(ci * wi for ci, wi in zip(sol, widths)) + cap_w
        else:
            t_min_x = cast(int, float("inf"))
            t_max_x = -t_min_x

        min_x = min(t_min_x, min(u.min_x() for u in self.units))
        max_x = max(t_max_x, max(u.max_x() for u in self.units))
        min_y = min(u.min_y() for u in self.units)
        max_y = max(u.max_y() for u in self.units)
        min_z = min(u.min_z() for u in self.units)
        max_z = max(u.max_z() for u in self.units)

        return min_x, min_y, min_z, max_x, max_y, max_z

    def draw_outline(self, region: Region, z_offset: int) -> None:
        assert (
            self.is_outline
        ), "This method is meant to be used for outline-generating subgroups"
        # at this point we're guaranteed to have exactly 2 units marked as outline corners
        corner1, corner2 = self.units
        material = corner1.region[0, 0, 0]
        # TODO: somehow handle X-dependent outline corners
        x1, x2 = corner1.region.x, corner2.region.x
        y = corner1.region.y
        z1, z2 = corner1.region.z, corner2.region.z
        assert x1 <= x2, "outline.corner1.x must be <= outline.corner2.x"
        assert z1 <= z2, "outline.corner1.z must be <= outline.corner2.z"
        if corner1.depends_on_z:
            z1 += z_offset
        make_rectangle_contour(region, y, x1, z1, x2, z2, material)

    def stack(self, region: Region, origin: tuple[int, int, int]) -> None:
        x0, y0, z0 = origin

        tiles: list[TilingUnit] = []
        cap = None
        for unit in self.units:
            if unit.x_dependence is XDependence.TILE:
                tiles.append(unit)
            elif unit.x_dependence is XDependence.CAP:
                cap = unit
        tiles.sort(key=lambda u: u.region.width, reverse=True)

        for unit in self.units:
            if unit.x_dependence is not XDependence.NONE:
                continue
            offset = (unit.region.x - x0, unit.region.y - y0, unit.region.z - z0)
            paste_region(region, unit.region, offset)

        if not tiles:
            return

        if cap:
            sol = self._knapsack_cache
        else:
            sol = knapsack_solver([u.region.width for u in tiles], region.width)

        x = min(u.min_x() for u in tiles) - x0
        for m, unit in zip(sol, tiles):
            y = unit.region.y - y0
            z = unit.region.z - z0
            for _ in range(m):
                paste_region(region, unit.region, (x, y, z), strict=bool(cap))
                x += unit.region.width

        if not cap:
            return
        y = cap.region.y - y0
        z = cap.region.z - z0
        paste_region(region, cap.region, (x, y, z))


class TilingGroup:
    def __init__(self, name: str):
        self.name: str = name
        self.subgroups: dict[str, TilingSubgroup] = {}

    def verify(self) -> None:
        for _, subgroup in self.subgroups.items():
            subgroup.verify(self.name)

    def add_unit(self, subgroup_name: str, unit: TilingUnit) -> None:
        if subgroup_name not in self.subgroups:
            self.subgroups[subgroup_name] = TilingSubgroup(subgroup_name)

        subgroup = self.subgroups[subgroup_name]
        subgroup.units.append(unit)

    def walk_units(self) -> Generator[TilingUnit, Any, None]:
        for subgroup in self.subgroups.values():
            yield from subgroup.units

    def get_x_offset(self, width: int) -> int:
        arr = [
            u.max_x()
            for u in self.walk_units()
            if u.x_dependence is not XDependence.NONE
        ]
        if not arr:
            return 0
        max_x_of_xdepenent = max(arr)
        return width - max_x_of_xdepenent

    def get_z_offset(self, length: int) -> int:
        arr = [u.max_z() for u in self.walk_units() if u.depends_on_z]
        if not arr:
            return 0
        max_z_of_zdepenent = max(arr)
        return length - max_z_of_zdepenent

    def get_box(self, width: int, length: int) -> tuple[int, int, int, int, int, int]:
        offset = self.get_z_offset(length)
        min_x = min_y = min_z = cast(int, float("inf"))
        max_x = max_y = max_z = -min_x

        outlines: list[TilingSubgroup] = []

        for subgr in self.subgroups.values():
            if subgr.is_outline:
                outlines.append(subgr)
                continue
            x0, y0, z0, x1, y1, z1 = subgr.get_box(width)
            if subgr.depends_on_z:
                z0 += offset
                z1 += offset
            min_x, max_x = min(min_x, x0), max(max_x, x1)
            min_y, max_y = min(min_y, y0), max(max_y, y1)
            min_z, max_z = min(min_z, z0), max(max_z, z1)

        for subgr in outlines:
            c0, c1 = subgr.units
            x0, y0, z0 = c0.min_x(), c0.min_y(), c0.min_z()
            x1, y1, z1 = c1.max_x(), c1.max_y(), c1.max_z()
            # How TF do I handle outlines? :sob:

        return min_x, min_y, min_z, max_x, max_y, max_z

    def stack(self, width: int, length: int) -> Region:
        x0, y0, z0, x1, y1, z1 = self.get_box(width, length)
        # create a large region for this group to be pasted into
        reg = Region(x0, y0, z0, x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1)
        z_offset = self.get_z_offset(length)
        # calculate local origin of this group
        if all(u.depends_on_z for u in self.walk_units()):
            local_origin = (reg.x, reg.y, reg.z - z_offset)
        else:
            local_origin = (reg.x, reg.y, reg.z)

        for subgr in self.subgroups.values():
            subgr.stack(reg, local_origin)
        return reg


class TilingTree:
    def __init__(self):
        self.name: str = "Unnamed"
        self.schem: Schematic = self._find_parts()
        self.groups: dict[str, TilingGroup] = {}

        for name, reg in self.schem.regions.items():
            unit = TilingUnit(name, reg)
            if unit.group not in self.groups:
                self.groups[unit.group] = TilingGroup(unit.group)
            group = self.groups[unit.group]
            if unit.subgroup is None:
                group.add_unit(f"{SEP}{unit.custom_id}", unit)
            else:
                group.add_unit(unit.subgroup, unit)

        for group in self.groups.values():
            group.verify()

    def _parse_name(self, path: str) -> None:
        fn = path.rsplit("/", maxsplit=1)[-1].rsplit("\\", maxsplit=1)[-1]
        self.name = fn[: -len("Parts.litematic")].strip()

    def _find_parts(self) -> Schematic:
        for path in listdir("."):
            if path.endswith("Parts.litematic"):
                self._parse_name(path)
                return Schematic.load(path)
        raise RuntimeError(
            "Couldn't find parts for tiling. Make sure you have a file"
            "ending with 'Parts.litematic' in the same directory with the program."
        )

    def needs_length(self) -> bool:
        for group in self.groups.values():
            if any(unit.depends_on_z for unit in group.walk_units()):
                return True
        return False

    def generate_schematic(
        self, width: int, length: int, author: str | None = None
    ) -> Schematic:
        if author is None:
            author = self.schem.author
        schem = Schematic(f"{self.name} {width}x{length}", author)
        for key, group in self.groups.items():
            schem.regions[key] = group.stack(width, length)
        return schem
