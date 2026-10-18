import capnp
import dataclasses
from enum import StrEnum
from typing import Any

from openpilot.cereal import custom
from opendbc.car import structs

_FIELDS = '__dataclass_fields__'  # copy of dataclasses._FIELDS


def is_dataclass(obj):
  """Similar to dataclasses.is_dataclass without instance type check checking"""
  return hasattr(obj, _FIELDS)


def _asdictref_inner(obj) -> dict[str, Any] | Any:
  if is_dataclass(obj):
    ret = {}
    for field in getattr(obj, _FIELDS):  # similar to dataclasses.fields()
      ret[field] = _asdictref_inner(getattr(obj, field))
    return ret
  elif isinstance(obj, (tuple, list)):
    return type(obj)(_asdictref_inner(v) for v in obj)
  else:
    return obj


def asdictref(obj) -> dict[str, Any]:
  """
  Similar to dataclasses.asdict without recursive type checking and copy.deepcopy
  Note that the resulting dict will contain references to the original struct as a result
  """
  if not is_dataclass(obj):
    raise TypeError("asdictref() should be called on dataclass instances")

  return _asdictref_inner(obj)


def convert_to_capnp(struct: structs.CarParamsSP | structs.CarStateSP) -> capnp.lib.capnp._DynamicStructBuilder:
  struct_dict = asdictref(struct)

  if isinstance(struct, structs.CarParamsSP):
    struct_capnp = custom.CarParamsSP.new_message(**struct_dict)
  elif isinstance(struct, structs.CarStateSP):
    struct_capnp = custom.CarStateSP.new_message(**struct_dict)
  else:
    raise ValueError(f"Unsupported struct type: {type(struct)}")

  return struct_capnp


def _plain_and_enum_fields(cls) -> tuple[tuple[str, ...], tuple[str, ...]]:
  # a field counts as an enum when its dataclass default is a StrEnum member (true for every car struct enum field)
  names = [f.name for f in dataclasses.fields(cls) if not f.name.endswith('DEPRECATED')]
  defaults = cls()
  enum_names = tuple(n for n in names if isinstance(getattr(defaults, n), StrEnum))
  return tuple(n for n in names if n not in enum_names), enum_names


# (field name, dataclass, plain field names, enum field names) for each CarControlSP sub-struct
_CAR_CONTROL_SP_SUBSTRUCTS = tuple((name, cls, *_plain_and_enum_fields(cls)) for name, cls in (
  ('mads', structs.ModularAssistiveDrivingSystem),
  ('leadOne', structs.LeadData),
  ('leadTwo', structs.LeadData),
  ('intelligentCruiseButtonManagement', structs.IntelligentCruiseButtonManagement),
))


def convert_carControlSP(struct: capnp.lib.capnp._DynamicStructReader) -> structs.CarControlSP:
  # Chipmunk OS 99: reads the reader directly instead of to_dict(), with the same result: enums come out as str,
  # an unset sub-struct keeps the dataclass defaults, params stays a list of dicts.
  struct_dataclass = structs.CarControlSP(params=[p.to_dict() for p in struct.params])
  for name, cls, plain_fields, enum_fields in _CAR_CONTROL_SP_SUBSTRUCTS:
    if struct._has(name):
      reader = getattr(struct, name)
      kwargs = {f: getattr(reader, f) for f in plain_fields}
      for f in enum_fields:
        kwargs[f] = getattr(reader, f)._as_str()
      setattr(struct_dataclass, name, cls(**kwargs))
  return struct_dataclass
