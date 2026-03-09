const fastify = require('fastify')({ logger: true });

fastify.get('/', async () => ({ hello: 'world' }));

fastify.listen({ port: 3000 });
