import { defineConfig } from 'vite';

export default defineConfig({
	// Relative URLs so dist/ works from any subpath (Stake Engine Files page,
	// S3 buckets, plain file servers) — never assume it is served from /.
	base: './',
	server: { port: 7921, host: true },
	preview: { port: 7922 },
	build: {
		outDir: 'dist',
		target: 'es2017',
		sourcemap: true,
	},
});
