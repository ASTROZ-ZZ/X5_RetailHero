-- Source: exported training orders, already unique at (client_id, transaction_id).
-- Amounts stored as integer cents to preserve reconciliation.
SELECT substr(o.transaction_datetime,1,10) AS Date, o.store_id AS Store,
       c.segment AS Segment, COUNT(*) AS Orders, SUM(o.cents) AS SalesCents
FROM orders o JOIN customers c USING(client_id)
GROUP BY substr(o.transaction_datetime,1,10), o.store_id, c.segment;
