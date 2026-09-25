import throttle from 'lodash/throttle';
export function useScroll(cb: () => void) {
  useEffect(() => {
    const h = throttle(cb, 100);
    window.addEventListener('scroll', h);
    return () => window.removeEventListener('scroll', h);
  }, [cb]);
}
