let
    Encoded = Text.Combine({"H4sIAAAAAAACEy2Qy2pCQRBE/8X15FL97v4WETFBiBsFlXx/6oYwq4E69ejj8fB5eV3P78OKTVERg7C0NqslW89owVXKolp7YYtIESuYVndaUoWSieSnQ9Oml21iBgozQ8OcGJbEwsJpMfH6ffm5PZ7/qQZCUdkDa6HfqFpg3KcZmju+Zw7cUwJwo9XWLURauhiOdqbShj2mJtsNqD2X9o1Q09A/kDVm6V7jdn9fn5ev9+1xP78Oy7dK0oodyaChbB5lw1PA+ZTLOFagdIp0NUnE+sBmmULvEUFpSbEKZkZGEVzFfrnL3Fm2EDyOVBin+uK40+kXgI5vi4YBAAA="}),
    Rows = Json.Document(Binary.Decompress(Binary.FromText(Encoded, BinaryEncoding.Base64), Compression.GZip)),
    Source = Table.FromRows(Rows, {"model","mean_uplift_pp","mean_vs_random_pp","sd_vs_random_pp","min_vs_random_pp","max_vs_random_pp","mean_vs_base_t_pp","folds_positive_vs_random","folds_positive_vs_base_t","repeats_positive_vs_base_t"}),
    Typed = Table.TransformColumnTypes(Source, {{"model", type text},{"mean_uplift_pp", type number},{"mean_vs_random_pp", type number},{"sd_vs_random_pp", type number},{"min_vs_random_pp", type number},{"max_vs_random_pp", type number},{"mean_vs_base_t_pp", type number},{"folds_positive_vs_random", Int64.Type},{"folds_positive_vs_base_t", Int64.Type},{"repeats_positive_vs_base_t", Int64.Type}}, "en-US")
in
    Typed