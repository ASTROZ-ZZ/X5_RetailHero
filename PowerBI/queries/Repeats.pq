let
    Encoded = Text.Combine({"H4sIAAAAAAACE22SS0pDQRBF9+L4+ah7678WCRIlYCYGYnD9VgcFB5k0Pej7OVX98vL0dvw6vd6eNmy+C9RS3ahoh2/YExUSTpiXOHSTXQ7bqE4fx+/z5fqnnGcIZmtoqvUoq8H2TGZ6VYwQyajmuCBLTZfP+fN2uh7fb+fL5+vXsrI9OjDxkgVT0bEyAZ1W0c7Ssu1Z9vGYoqLmMu1Y91K/KFyFWkskwqDazFWorKeid3RWsh+hLCVbqGRG9spdU+iCtmlyRSaWssMUAYYHuviAhcPibMDbWgQmMVakMEvMPFydvlimZZQlZjLDKfmfRaeRYWJnmGYBj9o48UabXJudzC0esSwl4U6NENqccV/L3NYeSiee91miu7I5nljM/QBmmQ15QdwFYmJcv8MlbJY8I9VxjPtiTL05D9TTGTgcfgByDkSPZQIAAA=="}),
    Rows = Json.Document(Binary.Decompress(Binary.FromText(Encoded, BinaryEncoding.Base64), Compression.GZip)),
    Source = Table.FromRows(Rows, {"model","repeat","uplift_pp","vs_random_pp","vs_base_t_pp"}),
    Typed = Table.TransformColumnTypes(Source, {{"model", type text},{"repeat", Int64.Type},{"uplift_pp", type number},{"vs_random_pp", type number},{"vs_base_t_pp", type number}}, "en-US")
in
    Typed