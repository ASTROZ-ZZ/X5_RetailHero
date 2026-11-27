let
    Encoded = Text.Combine({"H4sIAAAAAAACE13Ry0kDABAA0V48G8jO5ltLSP9tKAY0z+PcBt7j8dFxboeZQ/Px/HzLzDVP5tm8mFfzZt7JPb5lh+OYmWuezLN5Ma/mzbyT49V4NV6NV+PVeDVejVfj1XiVV3mVV3mVV3mVV3mVV3n1T3B/r+7fmm+gr8xc82SezYt5NW/mnfwDfaVX49V4NV6NV+PVeDVejVd5lVd5lVd5lVd5lVd5lVfrFaAJmqAJmqAJmqAJmqAJmqAJmqAJmqAJmqAJmqAJmqAJmqAJmqAJmqAJmqCr0Wq0Gq1Gq9FqtBqtRqvRarQarUar0Wq0Gq1Gq9H+GD2/ANFQX6frBgAA"}),
    Rows = Json.Document(Binary.Decompress(Binary.FromText(Encoded, BinaryEncoding.Base64), Compression.GZip)),
    Source = Table.FromRows(Rows, {"Date"}),
    Typed = Table.TransformColumnTypes(Source, {{"Date", type text}}, "en-US")
in
    Typed