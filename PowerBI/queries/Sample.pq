let
    Encoded = Text.Combine({"H4sIAAAAAAACE4uOVnq5qufF+saXs9uUYnWilZ53r3m+uvvJ/rnPp84Ei8UCAGCb5sgjAAAA"}),
    Rows = Json.Document(Binary.Decompress(Binary.FromText(Encoded, BinaryEncoding.Base64), Compression.GZip)),
    Source = Table.FromRows(Rows, {"Sample"}),
    Typed = Table.TransformColumnTypes(Source, {{"Sample", type text}}, "en-US")
in
    Typed