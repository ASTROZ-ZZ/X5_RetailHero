let
    Encoded = Text.Combine({"H4sIAAAAAAACExXNuw0CQRAD0F4uHlYzY89nazldSHYioxJEJ6R0g6iDJbXs533fvs/X5/3YJFVBiTm7BelWgraG6EiFF9t0Upll/wgZpolgKj0oGHBEO8PmjIZztbxV07kwLe2C+Khagpp5k0vNNexyTtY0YwElNirWDxlRmAnz6wUut/t5HscP9vUGf7EAAAA="}),
    Rows = Json.Document(Binary.Decompress(Binary.FromText(Encoded, BinaryEncoding.Base64), Compression.GZip)),
    Source = Table.FromRows(Rows, {"Segment","control_n","sms_n","control_buyers","sms_buyers","control_rate","sms_rate","difference_pp","standard_error_pp","ci_low_pp","ci_high_pp","p_value","holm_p"}),
    Typed = Table.TransformColumnTypes(Source, {{"Segment", type text},{"control_n", Int64.Type},{"sms_n", Int64.Type},{"control_buyers", Int64.Type},{"sms_buyers", Int64.Type},{"control_rate", type number},{"sms_rate", type number},{"difference_pp", type number},{"standard_error_pp", type number},{"ci_low_pp", type number},{"ci_high_pp", type number},{"p_value", type number},{"holm_p", type text}}, "en-US")
in
    Typed