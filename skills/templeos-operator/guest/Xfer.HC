// Xfer.HC — serial file-transfer helper for hermes-templeos
// Protocol: MAGIC "TXFR" | U8 cmd | U32 le len | payload | U32 le sum
//   sum = cmd + each payload byte (wrapping U32)
// Host cmds: 0x01 LIST, 0x02 PULL, 0x03 PUSH
// Guest replies: 0x81 LIST_OK, 0x82 PULL_OK, 0x83 PUSH_OK, 0x8F ERR
//
// TinkerOS: CommInit; CommInit8n1(1,115200); then #include this file
// and call XferServe; (or XferServeOnce; in a loop).
// Requires COM1 already open on the host before any guest write.

#define XFER_MAGIC0 'T'
#define XFER_MAGIC1 'X'
#define XFER_MAGIC2 'F'
#define XFER_MAGIC3 'R'
#define XFER_CMD_LIST 0x01
#define XFER_CMD_PULL 0x02
#define XFER_CMD_PUSH 0x03
#define XFER_CMD_LIST_OK 0x81
#define XFER_CMD_PULL_OK 0x82
#define XFER_CMD_PUSH_OK 0x83
#define XFER_CMD_ERR 0x8F
#define XFER_MAX 262144

U32 XferSum(U8 cmd, U8 *payload, U32 len)
{
  U32 s = cmd, i;
  for (i = 0; i < len; i++)
    s += payload[i];
  return s;
}

U0 XferPutU32(U32 v)
{
  CommPutChar(1, v.u8[0]);
  CommPutChar(1, v.u8[1]);
  CommPutChar(1, v.u8[2]);
  CommPutChar(1, v.u8[3]);
}

U8 XferGetChar()
{
  I64 c;
  while (1) {
    c = CommGetChar(1);
    if (c >= 0)
      return c;
    Yield;
  }
}

U32 XferGetU32()
{
  U32 v = 0;
  v.u8[0] = XferGetChar;
  v.u8[1] = XferGetChar;
  v.u8[2] = XferGetChar;
  v.u8[3] = XferGetChar;
  return v;
}

U0 XferSendFrame(U8 cmd, U8 *payload, U32 len)
{
  U32 i, sum;
  CommPutChar(1, XFER_MAGIC0);
  CommPutChar(1, XFER_MAGIC1);
  CommPutChar(1, XFER_MAGIC2);
  CommPutChar(1, XFER_MAGIC3);
  CommPutChar(1, cmd);
  XferPutU32(len);
  for (i = 0; i < len; i++)
    CommPutChar(1, payload[i]);
  sum = XferSum(cmd, payload, len);
  XferPutU32(sum);
}

U0 XferSendErr(U8 *msg)
{
  XferSendFrame(XFER_CMD_ERR, msg, StrLen(msg));
}

U0 XferSyncMagic()
{
  U8 b0 = 0, b1 = 0, b2 = 0, b3 = 0;
  while (1) {
    b0 = b1; b1 = b2; b2 = b3;
    b3 = XferGetChar;
    if (b0 == XFER_MAGIC0 && b1 == XFER_MAGIC1 &&
        b2 == XFER_MAGIC2 && b3 == XFER_MAGIC3)
      break;
  }
}

U0 XferHandleList(U8 *path)
{
  // Emit a tiny JSON array of names. Dir listing APIs vary by fork;
  // prefer FilesFind when present. On failure, return [].
  U8 buf[4096];
  I64 used = 0;
  CDirEntry *tmp = NULL, *de;
  buf[used++] = '[';
  try {
    tmp = FilesFind(path);
    de = tmp;
    while (de) {
      if (used > 1) {
        buf[used++] = ',';
      }
      // {"name":"...","is_dir":0|1}
      // Keep it short; host caps entries.
      CatPrint(buf + used, "{\"name\":\"%s\",\"is_dir\":%d}",
               de->name, !!(de->attr & RS_ATTR_DIR));
      used = StrLen(buf);
      if (used > 3500) break;
      de = de->next;
    }
  } catch {
    Fs->catch_except = TRUE;
  }
  if (tmp) DirTreeDel(tmp);
  buf[used++] = ']';
  buf[used] = 0;
  XferSendFrame(XFER_CMD_LIST_OK, buf, used);
}

U0 XferHandlePull(U8 *path)
{
  I64 size, i;
  U8 *data;
  size = FileSize(path);
  if (size < 0 || size > XFER_MAX) {
    XferSendErr("pull size");
    return;
  }
  data = FileRead(path, &size);
  if (!data) {
    XferSendErr("pull read");
    return;
  }
  XferSendFrame(XFER_CMD_PULL_OK, data, size);
  Free(data);
}

U0 XferHandlePush(U8 *payload, U32 len)
{
  U32 i = 0, path_len = 0;
  U8 path[256];
  U8 *data;
  I64 wrote;
  while (i < len && payload[i] && path_len < 255) {
    path[path_len++] = payload[i++];
  }
  path[path_len] = 0;
  if (i >= len || payload[i] != 0) {
    XferSendErr("push path");
    return;
  }
  i++; // skip NUL
  data = payload + i;
  wrote = FileWrite(path, data, len - i);
  if (wrote < 0) {
    XferSendErr("push write");
    return;
  }
  XferSendFrame(XFER_CMD_PUSH_OK, "", 0);
}

U0 XferServeOnce()
{
  U8 cmd;
  U32 len, sum, got, i;
  U8 *payload;
  XferSyncMagic;
  cmd = XferGetChar;
  len = XferGetU32;
  if (len > XFER_MAX) {
    // Drain and error.
    for (i = 0; i < len; i++) XferGetChar;
    XferGetU32; // discard sum
    XferSendErr("len");
    return;
  }
  payload = MAlloc(len + 1);
  for (i = 0; i < len; i++)
    payload[i] = XferGetChar;
  payload[len] = 0;
  sum = XferGetU32;
  got = XferSum(cmd, payload, len);
  if (sum != got) {
    Free(payload);
    XferSendErr("sum");
    return;
  }
  if (cmd == XFER_CMD_LIST)
    XferHandleList(payload);
  else if (cmd == XFER_CMD_PULL)
    XferHandlePull(payload);
  else if (cmd == XFER_CMD_PUSH)
    XferHandlePush(payload, len);
  else
    XferSendErr("cmd");
  Free(payload);
}

U0 XferServe()
{
  while (1)
    XferServeOnce;
}
