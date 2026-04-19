async function(page) {
  const left = page.locator('[data-testid="stSlider"] [role="slider"]').nth(0);
  const before = await left.getAttribute('aria-valuetext');
  const box = await left.boundingBox();
  if (!box) return { before, error: 'no box' };
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2, { steps: 12 });
  await page.mouse.up();
  await page.waitForTimeout(700);
  const after = await left.getAttribute('aria-valuetext');
  const boxAfter = await left.boundingBox();
  return { before, after, beforeBox: box, afterBox: boxAfter };
}
