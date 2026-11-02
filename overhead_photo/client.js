import { render } from '../overhead_core/static/overhead.js';

export default async function (shadow, ctx) {
  await render(shadow, ctx, 'photo');
}
