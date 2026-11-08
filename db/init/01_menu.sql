-- Seed data for the Compose demo: the NovaStack menu as a table.
-- Postgres runs every file in /docker-entrypoint-initdb.d once, the first time
-- the database is created (an empty volume).
CREATE TABLE items (
  sku       text PRIMARY KEY,
  name      text NOT NULL,
  category  text NOT NULL,
  price     numeric(6, 2) NOT NULL
);

INSERT INTO items (sku, name, category, price) VALUES
  ('M01', 'Chicken wrap', 'main', 5.20),
  ('M02', 'Falafel wrap', 'main', 4.90),
  ('M03', 'Beef burger', 'main', 6.80),
  ('M04', 'Halloumi burger', 'main', 6.40),
  ('M05', 'Jacket potato, beans', 'main', 4.20),
  ('M06', 'Katsu curry', 'main', 7.10),
  ('S01', 'Fries', 'side', 2.10),
  ('S02', 'Sweet potato fries', 'side', 2.60),
  ('S03', 'Side salad', 'side', 1.90),
  ('S04', 'Onion rings', 'side', 2.30),
  ('D01', 'Cola', 'drink', 1.60),
  ('D02', 'Orange juice', 'drink', 1.80),
  ('D03', 'Sparkling water', 'drink', 1.20),
  ('D04', 'Flat white', 'drink', 2.95),
  ('P01', 'Brownie', 'dessert', 2.40),
  ('P02', 'Fruit pot', 'dessert', 1.95),
  ('N01', 'Crisps', 'snack', 0.95),
  ('N02', 'Flapjack', 'snack', 1.45);
