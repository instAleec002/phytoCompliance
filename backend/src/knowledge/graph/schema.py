"""Schema of the phytosanitary graph (Apache AGE, graph ``fito``).

Nodes (label: key property)
    Crop            key            "blueberry"; SIGIA and EU ids
    Pest            key            SIGIA pest id, or "use:<class>" for an "other use" (e.g. foliar applications)
    Product         key            SIGIA product id; trade name, registration number, holder, chemical or biological
    Authorization   key            "<product>:<crop>:<pest>"; one registered use with its dose, Peru MRL and
                                   pre-harvest interval
    Ingredient      key            ISO common name after normalization ("pyraclostrobin")
    Residue         key            "EU:<residue id>"; the residue definition the EU sets limits for
    Market          key            "EU", "US", "CODEX"
    MrlVersion      key            "EU:<product id>:<residue id>:<annex>"; one version of one limit, never overwritten
    MoaGroup        key            "FRAC:11", "IRAC:4A", "HRAC:9"; a mode-of-action group with its scheme edition

Edges
    (Authorization)-[:OF_PRODUCT]->(Product)
    (Authorization)-[:ON_CROP]->(Crop)
    (Authorization)-[:AGAINST]->(Pest)
    (Product)-[:CONTAINS]->(Ingredient)
    (Ingredient)-[:MEASURED_AS]->(Residue)          from the normalization (knowledge.normalization)
    (MrlVersion)-[:OF_RESIDUE]->(Residue)
    (MrlVersion)-[:FOR_CROP]->(Crop)
    (MrlVersion)-[:IN_MARKET]->(Market)
    (MrlVersion)-[:REPLACES]->(MrlVersion)          newer version -> the one it replaced
    (Ingredient)-[:IN_GROUP]->(MoaGroup)            from the FRAC, IRAC and HRAC lists (knowledge.normalization.moa)

Every node and edge loaded from a source carries ``snapshot`` (source and date), so any value can be traced back to the
dated download it came from.
"""

GRAPH = "fito"

NODE_LABELS = ("Crop", "Pest", "Product", "Authorization", "Ingredient", "Residue", "Market", "MrlVersion", "MoaGroup")
EDGE_TYPES = ("OF_PRODUCT", "ON_CROP", "AGAINST", "CONTAINS", "MEASURED_AS", "OF_RESIDUE", "FOR_CROP", "IN_MARKET",
              "REPLACES", "IN_GROUP")
