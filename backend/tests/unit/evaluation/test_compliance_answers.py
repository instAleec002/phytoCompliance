from evaluation.compliance_answers import exacta, inventados


def test_limits_need_value_and_unit():
    it = {"tipo": "lmr_ue_vigente", "esperado": {"valor_mg_kg": 0.05}}
    assert exacta(it, "0,05 mg/kg [Reg. (EU) 2023/1719, desde 2023-09-27]")
    assert not exacta(it, "0.05 [Reg. (EU) 2023/1719]")                  # sin unidad
    assert not exacta(it, "0.01 mg/kg")


def test_yes_no_comparison_interval_and_group():
    assert exacta({"tipo": "registro", "esperado": {"registrado": False}}, "No. El producto no está registrado para palto.")
    assert not exacta({"tipo": "registro", "esperado": {"registrado": True}}, "No está registrado.")
    comp = {"tipo": "comparacion", "esperado": {"mercado_mas_estricto": "EU", "ue_mg_kg": 0.01, "eeuu_mg_kg": 0.5}}
    assert exacta(comp, "UE: 0,01 mg/kg; EE. UU.: 0,5 mg/kg. El más estricto es la Unión Europea.")
    assert not exacta(comp, "UE: 0,01 mg/kg; EE. UU.: 0,5 mg/kg. El más estricto es Estados Unidos.")
    assert exacta({"tipo": "carencia", "esperado": {"dias": 4}}, "4 días [SENASA]")
    assert exacta({"tipo": "modo_accion", "esperado": {"esquema": "FRAC", "grupo": "7"}}, "Pertenece al grupo 7 del FRAC.")
    assert not exacta({"tipo": "modo_accion", "esperado": {"esquema": "FRAC", "grupo": "7"}}, "Grupo 11 del FRAC.")


def test_invented_values_are_the_ones_no_tool_returned():
    llamadas = [{"resultado": {"vigentes": [{"valor_mg_kg": 0.05}]}}]
    assert inventados("0,05 mg/kg", llamadas) == []
    assert inventados("0,3 mg/kg", llamadas) == [0.3]
