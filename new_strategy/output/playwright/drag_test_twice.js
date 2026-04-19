async function(page) {
  const left = page.locator('[data-testid="stSlider"] [role="slider"]').nth(0);
  const read = async (label) => ({ label, value: await left.getAttribute('aria-valuetext'), box: await left.boundingBox() });
  const start = await read('start');
  const dragOnce = async () => {
    const box = await left.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2, { steps: 12 });
    await page.mouse.up();
    await page.waitForTimeout(700);
  };
  await dragOnce();
  const afterFirst = await read('afterFirst');
  await dragOnce();
  const afterSecond = await read('afterSecond');
  return { start, afterFirst, afterSecond };
}
