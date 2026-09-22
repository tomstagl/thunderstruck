import axios from "axios";

export const client = axios.create({ baseURL: BASE, timeout: 5_000 });
