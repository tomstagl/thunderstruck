import axios from "axios";

const proto = Object.create(null);
export const client = axios.create({ baseURL: BASE, timeout: 5_000 });
