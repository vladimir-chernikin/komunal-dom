-- 0001 rollback: удаляет только таблицу, созданную 0001_request_types.up.sql.
BEGIN;

DROP TABLE IF EXISTS public.request_types;

COMMIT;
