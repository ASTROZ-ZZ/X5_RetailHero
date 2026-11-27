let
    Encoded = Text.Combine({"H4sIAAAAAAACE4uOVnq5esaT3dufNux5tmX3i+3NSrE6SGJP97U+nbLkZdsksPCL/ROfzZmPpO7J3j4Msaet257snvZ03aJnHduVYmMBqttaIWIAAAA="}),
    Rows = Json.Document(Binary.Decompress(Binary.FromText(Encoded, BinaryEncoding.Base64), Compression.GZip)),
    Source = Table.FromRows(Rows, {"Segment"}),
    Typed = Table.TransformColumnTypes(Source, {{"Segment", type text}}, "en-US")
in
    Typed