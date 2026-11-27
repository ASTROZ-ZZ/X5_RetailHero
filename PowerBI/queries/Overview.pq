let
    Encoded = Text.Combine({"H4sIAAAAAAACEw3JwREAQAQDwIY8knDoxei/jfPc2ZkAmLJ41fmyjQIkU5BdMsK9owA/XFG++wFwK1F2NgAAAA=="}),
    Rows = Json.Document(Binary.Decompress(Binary.FromText(Encoded, BinaryEncoding.Base64), Compression.GZip)),
    Source = Table.FromRows(Rows, {"HistoryClients","Lines","TrainClients","TrainOrders","SalesCents","OfficialScores"}),
    Typed = Table.TransformColumnTypes(Source, {{"HistoryClients", Int64.Type},{"Lines", Int64.Type},{"TrainClients", Int64.Type},{"TrainOrders", Int64.Type},{"SalesCents", Int64.Type},{"OfficialScores", Int64.Type}}, "en-US")
in
    Typed