import dataclasses
import random

from openpilot.cereal import custom
from openpilot.selfdrive.car.helpers import _CAR_CONTROL_SP_SUBSTRUCTS, convert_carControlSP
from opendbc.car import structs


def convert_carControlSP_via_to_dict(struct) -> structs.CarControlSP:
  """The pre-99 implementation (capnp to_dict() + dataclass rebuild), kept as the equivalence reference."""
  def remove_deprecated(s: dict) -> dict:
    return {k: v for k, v in s.items() if not k.endswith('DEPRECATED')}

  struct_dict = struct.to_dict()
  struct_dataclass = structs.CarControlSP(**remove_deprecated({k: v for k, v in struct_dict.items() if not isinstance(k, dict)}))
  struct_dataclass.mads = structs.ModularAssistiveDrivingSystem(**remove_deprecated(struct_dict.get('mads', {})))
  struct_dataclass.leadOne = structs.LeadData(**remove_deprecated(struct_dict.get('leadOne', {})))
  struct_dataclass.leadTwo = structs.LeadData(**remove_deprecated(struct_dict.get('leadTwo', {})))
  struct_dataclass.intelligentCruiseButtonManagement = structs.IntelligentCruiseButtonManagement(
    **remove_deprecated(struct_dict.get('intelligentCruiseButtonManagement', {}))
  )
  return struct_dataclass


MADS_STATES = list(structs.ModularAssistiveDrivingSystem.ModularAssistiveDrivingSystemState)
ICBM_STATES = list(structs.IntelligentCruiseButtonManagement.IntelligentCruiseButtonManagementState)
SEND_BUTTONS = list(structs.IntelligentCruiseButtonManagement.SendButtonState)
PARAM_TYPES = list(structs.CarControlSP.ParamType)


def fill_lead(lead, rng: random.Random):
  for name in ('dRel', 'yRel', 'vRel', 'aRel', 'vLead', 'dPath', 'vLat', 'vLeadK', 'aLeadK', 'aLeadTau', 'modelProb', 'aLeadDEPRECATED'):
    setattr(lead, name, rng.uniform(-200., 200.))
  for name in ('fcw', 'status', 'radar'):
    setattr(lead, name, rng.random() < 0.5)
  lead.radarTrackId = rng.choice([-1, 0, rng.randint(-2**31, 2**31 - 1)])


def random_carControlSP(rng: random.Random):
  msg = custom.CarControlSP.new_message()
  # each sub-struct is sometimes left unset: to_dict() then omits it and the dataclass defaults apply
  if rng.random() < 0.8:
    msg.mads.state = rng.choice(MADS_STATES).value
    msg.mads.enabled = rng.random() < 0.5
    msg.mads.active = rng.random() < 0.5
    msg.mads.available = rng.random() < 0.5
  if rng.random() < 0.8:
    fill_lead(msg.leadOne, rng)
  if rng.random() < 0.8:
    fill_lead(msg.leadTwo, rng)
  if rng.random() < 0.8:
    icbm = msg.intelligentCruiseButtonManagement
    icbm.state = rng.choice(ICBM_STATES).value
    icbm.sendButton = rng.choice(SEND_BUTTONS).value
    icbm.vTarget = rng.uniform(0., 50.)
  if rng.random() < 0.3:
    params = msg.init('params', rng.randint(0, 3))
    for p in params:
      if rng.random() < 0.7:
        p.key = f"k{rng.randint(0, 99)}"
      if rng.random() < 0.7:
        p.value = rng.randbytes(rng.randint(0, 8))
      p.type = rng.choice(PARAM_TYPES).value
  return msg.as_reader()


def non_deprecated(names) -> set[str]:
  return {n for n in names if not n.endswith('DEPRECATED')}


def assert_same_values_and_types(new, ref, path='CarControlSP'):
  assert type(new) is type(ref), f"{path}: {type(new)} != {type(ref)}"
  if dataclasses.is_dataclass(ref):
    for f in dataclasses.fields(ref):
      assert_same_values_and_types(getattr(new, f.name), getattr(ref, f.name), f"{path}.{f.name}")
  elif isinstance(ref, list):
    assert len(new) == len(ref), path
    for i, (n, r) in enumerate(zip(new, ref, strict=True)):
      assert_same_values_and_types(n, r, f"{path}[{i}]")
  else:
    assert new == ref, f"{path}: {new!r} != {ref!r}"


class TestConvertCarControlSP:
  def test_empty_message(self):
    struct = custom.CarControlSP.new_message().as_reader()
    assert_same_values_and_types(convert_carControlSP(struct), convert_carControlSP_via_to_dict(struct))

  def test_controlsd_shape_message(self):
    # what controlsd_ext publishes: all four sub-structs set, no params, capnp default radarTrackId -1
    msg = custom.CarControlSP.new_message()
    msg.leadOne.radarTrackId = -1
    msg.leadTwo.radarTrackId = -1
    msg.mads.state = 'enabled'
    msg.intelligentCruiseButtonManagement.sendButton = 'increase'
    struct = msg.as_reader()
    assert_same_values_and_types(convert_carControlSP(struct), convert_carControlSP_via_to_dict(struct))

  def test_random_messages(self):
    rng = random.Random(99)
    for _ in range(500):
      struct = random_carControlSP(rng)
      assert_same_values_and_types(convert_carControlSP(struct), convert_carControlSP_via_to_dict(struct))

  def test_partially_set_substructs(self):
    # setting one field allocates the sub-struct, so the rest are capnp defaults (radarTrackId -1), not dataclass defaults
    for name, field, value in (('leadOne', 'dRel', 12.5), ('leadTwo', 'radar', True), ('mads', 'enabled', True),
                               ('intelligentCruiseButtonManagement', 'vTarget', 20.)):
      msg = custom.CarControlSP.new_message()
      setattr(getattr(msg, name), field, value)
      struct = msg.as_reader()
      assert_same_values_and_types(convert_carControlSP(struct), convert_carControlSP_via_to_dict(struct))


class TestCarControlSPStructsInSync:
  """convert_carControlSP copies only registered sub-structs and known fields; a new capnp or dataclass field must fail here."""

  def test_top_level_fields(self):
    capnp_names = non_deprecated(custom.CarControlSP.schema.fields)
    dataclass_names = non_deprecated(f.name for f in dataclasses.fields(structs.CarControlSP))
    registered_names = {'params'} | {name for name, *_ in _CAR_CONTROL_SP_SUBSTRUCTS}
    assert capnp_names == dataclass_names == registered_names

  def test_substruct_fields(self):
    msg = custom.CarControlSP.new_message()
    for name, cls, plain_fields, enum_fields in _CAR_CONTROL_SP_SUBSTRUCTS:
      capnp_fields = getattr(msg, name).schema.fields
      capnp_names = non_deprecated(capnp_fields)
      dataclass_names = non_deprecated(f.name for f in dataclasses.fields(cls))
      assert capnp_names == dataclass_names == set(plain_fields) | set(enum_fields), name
      capnp_enum_names = {n for n in capnp_names if capnp_fields[n].proto.slot.type.which() == 'enum'}
      assert capnp_enum_names == set(enum_fields), name
