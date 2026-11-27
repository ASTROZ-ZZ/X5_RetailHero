let
    Encoded = Text.Combine({"H4sIAAAAAAACE52UXW6DMAyA78IzrWI7vxfYCfZWVRXrkIpESwVppd1+pIFgtG4rvFiRiD/ZX2x2uwwF2A1Alot8OmsDIIeYvRV1V2Z5di1aXxX1oTj66l75r8O5ufhTll9udb3PGQlGEiaSlIA/Scfm1LT+Vw4+OG4jpopQWbWYQyNnqoecpcUcOXJo6qsHLTWEzHV/JkkGhpi9t7cAOjbna136/ghbMcsE5iTmoJXaPMkUW4sW0YTv6KSVMAMhkzKUINCp5yALEkArBUZKFDQDEbMygMCRSKCXpSS9cgSFK4nT3HxXfZaH5qMr23vhq+Yyg0QngvnpG4cY/vIa7wLT8UgxKOG5DKWscEJogUYrTTMMMhkRY8ktUTG8LFPxwKwwkXSqlQxkNsPmKKFi+Mcmn1Ia8lQ/ggs18BmVA2ZFC8Q0rGUklXolg5jKsCYqbEkIS34dMRf4lqi0JCPntWKQSVkNIWZlNSSpNQsh+29n3bIUvAYAAA=="}),
    Rows = Json.Document(Binary.Decompress(Binary.FromText(Encoded, BinaryEncoding.Base64), Compression.GZip)),
    Source = Table.FromRows(Rows, {"cohort_month","month_offset","activity_month","cohort_customers","active_customers_observed","cohort_month_complete","status","repeat_rate"}),
    Typed = Table.TransformColumnTypes(Source, {{"cohort_month", type text},{"month_offset", Int64.Type},{"activity_month", type text},{"cohort_customers", Int64.Type},{"active_customers_observed", Int64.Type},{"cohort_month_complete", type text},{"status", type text},{"repeat_rate", type number}}, "en-US")
in
    Typed