-- Expand step: the running old version keeps reading and writing username.
ALTER TABLE users ADD COLUMN handle TEXT;
