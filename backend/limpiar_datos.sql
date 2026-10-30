-- =============================================================================
-- Borra TODO lo creado por probar_api.py:
--   * los usuarios con email que termina en @prueba.test
--   * los negocios en los que esos usuarios trabajan (y todo lo que cuelga de ellos)
--
-- Úsalo en pgAdmin (Query Tool). Está en una sola transacción: si algo falla,
-- no se borra nada.
--
-- PASO 1 (recomendado): corre solo este SELECT para ver qué se va a borrar.
-- =============================================================================
SELECT
    (SELECT count(*) FROM usuario WHERE email LIKE '%@prueba.test')           AS usuarios_de_prueba,
    (SELECT count(DISTINCT un.negocio_id)
       FROM usuario_negocio un JOIN usuario u ON u.id = un.usuario_id
      WHERE u.email LIKE '%@prueba.test')                                      AS negocios_de_prueba;

-- Si los números tienen sentido (4 usuarios y 2 negocios por cada corrida del
-- script), pasa al PASO 2.
--
-- PASO 2: borrar. (Selecciona desde BEGIN hasta COMMIT y ejecuta.)
-- =============================================================================
BEGIN;

CREATE TEMP TABLE _negocios_prueba ON COMMIT DROP AS
SELECT DISTINCT un.negocio_id AS id
FROM usuario_negocio un
JOIN usuario u ON u.id = un.usuario_id
WHERE u.email LIKE '%@prueba.test';

-- Lo más "profundo" primero (hojas del esquema), hacia arriba:
DELETE FROM productos_de_cita
 WHERE cita_id IN (SELECT id FROM cita WHERE negocio_id IN (SELECT id FROM _negocios_prueba));

DELETE FROM servicios_de_cita
 WHERE cita_id IN (SELECT id FROM cita WHERE negocio_id IN (SELECT id FROM _negocios_prueba));

DELETE FROM cita
 WHERE negocio_id IN (SELECT id FROM _negocios_prueba);

DELETE FROM pausa
 WHERE horario_id IN (
        SELECT h.id
          FROM horario h
          JOIN usuario_negocio un ON un.id = h.usuario_negocio_id
         WHERE un.negocio_id IN (SELECT id FROM _negocios_prueba));

DELETE FROM horario
 WHERE usuario_negocio_id IN (
        SELECT id FROM usuario_negocio WHERE negocio_id IN (SELECT id FROM _negocios_prueba));

DELETE FROM empleado_servicio
 WHERE servicio_id IN (SELECT id FROM servicio WHERE negocio_id IN (SELECT id FROM _negocios_prueba));

DELETE FROM producto        WHERE negocio_id IN (SELECT id FROM _negocios_prueba);
DELETE FROM servicio        WHERE negocio_id IN (SELECT id FROM _negocios_prueba);
DELETE FROM cliente         WHERE negocio_id IN (SELECT id FROM _negocios_prueba);
DELETE FROM usuario_negocio WHERE negocio_id IN (SELECT id FROM _negocios_prueba);
DELETE FROM negocio         WHERE id          IN (SELECT id FROM _negocios_prueba);

-- Al final, las cuentas (también las que nunca llegaron a tener negocio, como Dani)
DELETE FROM usuario WHERE email LIKE '%@prueba.test';

COMMIT;

-- Comprobación: debe devolver 0 y 0
SELECT (SELECT count(*) FROM usuario WHERE email LIKE '%@prueba.test') AS usuarios_que_quedan,
       (SELECT count(*) FROM negocio WHERE nombre LIKE 'TEST %')       AS negocios_que_quedan;