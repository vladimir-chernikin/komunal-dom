-- 0001: перенос справочника «ТипОбращения» из А в Б.
-- Источник: public.ref_service_types (А), подтвержден read-only выборкой.
-- Область: только public.request_types.
BEGIN;

CREATE TABLE IF NOT EXISTS public.request_types (
    id smallint PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL UNIQUE,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.request_types (id, code, name)
VALUES
    (1, 'incident', 'Инцидент'),
    (2, 'request', 'Запрос')
ON CONFLICT (id) DO NOTHING;

COMMIT;
