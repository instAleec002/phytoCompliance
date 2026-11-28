"""Field order of the SIGIA answers.

SIGIA (SENASA's pesticide registry) answers with positional lists, not objects. The names below are the ones the
official web client uses for its grids (``consultas/cultivo.js``, ``cultivo_plaga.js`` and
``cultivo_plaga_producto.js``, checked on 27/10/2026), so each position is identified, not guessed.
"""

CROP_FIELDS = ["cultivoid", "cultivonombrecientifico", "cultivonombrecomun"]

PEST_FIELDS = ["plagaid", "plaganombrecientifico", "plaganombrecomun", "check", "idclaseotrouso"]

PRODUCT_FIELDS = [
    "productoid", "nombrecomercial", "empresaid", "razonsocial", "numeroregistro", "ingredienteactivo", "clase",
    "categoriatoxicologico", "cultivoid", "plagaid", "cultivonombrecientifico", "plaganombrecientifico",
    "cultivonombrecomun", "plaganombrecomun", "unidadmedida", "dosishectarea", "dosisporcentaje", "capacidadcilindro",
    "dosiscilindro", "limitemaximoresiduo", "periodocarenciadias", "observacion", "tipoproducto", "principiosactivos",
]
