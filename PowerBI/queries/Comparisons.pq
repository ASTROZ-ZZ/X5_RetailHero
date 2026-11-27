let
    Encoded = Text.Combine({"H4sIAAAAAAACE4WRS06UURCF9/KPrzf1OPVaCyGkwVcnSJOmGTB04gSnDoxxA0LiEtyMScMuKIwDQ1Qmd3RzvvOdOjhYdkenmzfri936ZBnLdnX2cvNuGTphJFFSYp5kisFTgyVCTYkNmjpsWn9IFhUWcq8hNT1S00vNmAI5lvtvH+++v7//8mE5HE9xr5uFaZapbtnR0u+QCSGGF8AJlbDh0ytMXEQyKTW6j7trZpM4AkH6X9T55fbk7eri1dH5dnO8Ol6frndXj2wXVFXbdHYRN9uYU6miKiGaaHZoskekG9gc/UndJbpLlAnRM5a/R6UphdJypEQG13jBs1OBDqoClbn8yu42bOmo1MJQmgy0fmurEzCW/fXt/ub654+v+0+f/71su/TtCtJ+5Fxp3QFK6GshM8ysV0PrUYSbZscnHqf9E6c9z1+Ihw+RUjgCPAIAAA=="}),
    Rows = Json.Document(Binary.Decompress(Binary.FromText(Encoded, BinaryEncoding.Base64), Compression.GZip)),
    Source = Table.FromRows(Rows, {"policy","comparator","difference_pp","ci_low_pp","ci_high_pp","overlap_pct","Sample"}),
    Typed = Table.TransformColumnTypes(Source, {{"policy", type text},{"comparator", type text},{"difference_pp", type number},{"ci_low_pp", type number},{"ci_high_pp", type number},{"overlap_pct", type number},{"Sample", type text}}, "en-US")
in
    Typed