/**
 * Kiroku Outreach Automation
 * Human-in-the-loop rule: only rows approved by Mariam are sent.
 */

const SHEET_NAME = 'Cadence';
const MAX_SENDS_PER_RUN = 10;
const DISCORD_WEBHOOK_PROPERTY = 'DISCORD_WEBHOOK_URL';
const DISCORD_MARIAM_ROLE_ID_PROPERTY = 'DISCORD_MARIAM_ROLE_ID';
const DISCORD_BOT_TOKEN_PROPERTY = 'DISCORD_BOT_TOKEN';
const DISCORD_COMMAND_CHANNEL_IDS_PROPERTY = 'DISCORD_COMMAND_CHANNEL_IDS';
const DISCORD_ALLOWED_USER_IDS_PROPERTY = 'DISCORD_ALLOWED_USER_IDS';
const DISCORD_LAST_MSG_PREFIX = 'DISCORD_LAST_COMMAND_MESSAGE_ID_';
const DISCORD_COMMAND_PREFIX = '!kiroku';

function validateConfiguration() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error(`Sheet ${SHEET_NAME} not found`);

  const headers = getHeaders_(sheet);
  const required = [
    'recipient_email',
    'approval_status',
    'send_lock',
    'active_touch',
    'send_status',
    'week1_date',
    'week1_subject',
    'week1_email_body',
    'week2_date',
    'week2_subject',
    'week2_email_body',
    'week3_date',
    'week3_subject',
    'week3_email_body',
    'sent_at',
    'gmail_message_id',
    'gmail_thread_id',
    'next_followup_date',
    'week1_status',
    'week2_status',
    'week3_status',
    'week1_notes',
    'week2_notes',
    'week3_notes',
    'reply_status'
  ];

  const missing = required.filter((k) => !(k in headers));
  if (missing.length) {
    throw new Error(`Missing required columns: ${missing.join(', ')}`);
  }

  Logger.log('Configuration OK');
  Logger.log(`Discord webhook configured: ${Boolean(getDiscordWebhookUrl_())}`);
  Logger.log(`Discord command bridge configured: ${Boolean(getDiscordBotToken_()) && getDiscordCommandChannelIds_().length > 0}`);
}

function sendApprovedDueEmails() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error(`Sheet ${SHEET_NAME} not found`);

  const headers = getHeaders_(sheet);
  const data = getRows_(sheet);
  const today = todayYmd_();

  let sentCount = 0;
  const sentEvents = [];
  const failedEvents = [];

  for (let i = 0; i < data.length; i++) {
    if (sentCount >= MAX_SENDS_PER_RUN) break;

    const rowNum = i + 2;
    const row = data[i];

    const approval = String(getValue_(row, headers, 'approval_status')).trim();
    const sendLock = String(getValue_(row, headers, 'send_lock')).trim();
    const recipient = String(getValue_(row, headers, 'recipient_email')).trim();
    const activeTouch = String(getValue_(row, headers, 'active_touch')).trim() || 'week1';
    const sendStatus = String(getValue_(row, headers, 'send_status')).trim();
    const company = String(getValue_(row, headers, 'company')).trim();
    const contactName = String(getValue_(row, headers, 'decision_maker_name')).trim();
    const track = String(getValue_(row, headers, 'track')).trim();

    if (approval !== 'APPROVED') continue;
    if (sendLock !== 'UNLOCKED') continue;
    if (!recipient) continue;
    if (sendStatus === 'SENT') continue;

    const dateCol = `${activeTouch}_date`;
    const subjectCol = `${activeTouch}_subject`;
    const bodyCol = `${activeTouch}_email_body`;
    const touchStatusCol = `${activeTouch}_status`;
    const touchNotesCol = `${activeTouch}_notes`;

    const dueDate = String(getValue_(row, headers, dateCol)).trim();
    const subject = String(getValue_(row, headers, subjectCol)).trim();
    const body = String(getValue_(row, headers, bodyCol)).trim();

    if (!dueDate || dueDate > today) continue;
    if (!subject || !body) continue;

    try {
      const draft = GmailApp.createDraft(recipient, subject, body);
      const message = draft.getMessage();
      message.send();

      const thread = message.getThread();

      setValue_(sheet, rowNum, headers, 'send_status', 'SENT');
      setValue_(sheet, rowNum, headers, 'sent_at', nowIso_());
      setValue_(sheet, rowNum, headers, 'gmail_message_id', message.getId());
      setValue_(sheet, rowNum, headers, 'gmail_thread_id', thread.getId());
      setValue_(sheet, rowNum, headers, touchStatusCol, 'SENT');

      const prevNote = String(getValue_(row, headers, touchNotesCol) || '');
      const append = ` [auto-send ${nowIso_()}]`;
      setValue_(sheet, rowNum, headers, touchNotesCol, `${prevNote}${append}`.trim());

      if (activeTouch === 'week1') {
        setValue_(sheet, rowNum, headers, 'active_touch', 'week2');
        setValue_(sheet, rowNum, headers, 'send_status', 'NOT_SENT');
        setValue_(sheet, rowNum, headers, 'next_followup_date', getValue_(row, headers, 'week2_date'));
      } else if (activeTouch === 'week2') {
        setValue_(sheet, rowNum, headers, 'active_touch', 'week3');
        setValue_(sheet, rowNum, headers, 'send_status', 'NOT_SENT');
        setValue_(sheet, rowNum, headers, 'next_followup_date', getValue_(row, headers, 'week3_date'));
      } else {
        setValue_(sheet, rowNum, headers, 'next_followup_date', '');
      }

      sentCount += 1;
      sentEvents.push(`SENT ${activeTouch}: ${track} | ${company} | ${contactName} | ${recipient}`);
      Utilities.sleep(1200); // gentle throttle
    } catch (err) {
      setValue_(sheet, rowNum, headers, 'send_status', 'FAILED');
      const noteCol = `${activeTouch}_notes`;
      const prev = String(getValue_(row, headers, noteCol) || '');
      const errMsg = String(err);
      setValue_(sheet, rowNum, headers, noteCol, `${prev} [send-error ${errMsg}]`.trim());
      failedEvents.push(`FAILED ${activeTouch}: ${track} | ${company} | ${contactName} | ${recipient} | ${errMsg}`);
    }
  }

  Logger.log(`Sent ${sentCount} message(s)`);
  if (sentEvents.length || failedEvents.length) {
    const lines = [
      `Sheet: ${SHEET_NAME}`,
      `Date: ${today}`,
      `Sent: ${sentEvents.length}`,
      `Failed: ${failedEvents.length}`
    ];
    if (sentEvents.length) lines.push(...sentEvents);
    if (failedEvents.length) lines.push(...failedEvents);
    notifyDiscord_(failedEvents.length ? 'Outreach Send Run (with failures)' : 'Outreach Send Run', lines, {
      mentionMariam: failedEvents.length > 0
    });
  }
}

function syncRepliesByThread() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error(`Sheet ${SHEET_NAME} not found`);

  const headers = getHeaders_(sheet);
  const data = getRows_(sheet);
  const replyEvents = [];

  for (let i = 0; i < data.length; i++) {
    const rowNum = i + 2;
    const row = data[i];

    const threadId = String(getValue_(row, headers, 'gmail_thread_id')).trim();
    const replyStatus = String(getValue_(row, headers, 'reply_status')).trim() || 'NO_REPLY';
    const company = String(getValue_(row, headers, 'company')).trim();
    const contactName = String(getValue_(row, headers, 'decision_maker_name')).trim();
    const track = String(getValue_(row, headers, 'track')).trim();
    if (!threadId) continue;

    try {
      const thread = GmailApp.getThreadById(threadId);
      if (!thread) continue;

      const messages = thread.getMessages();
      if (messages.length <= 1) continue; // only outbound exists
      if (replyStatus !== 'NO_REPLY') continue; // already handled

      // If there are 2+ messages, we assume at least one response/reply on thread.
      setValue_(sheet, rowNum, headers, 'reply_status', 'REPLIED_NEUTRAL');
      setValue_(sheet, rowNum, headers, 'last_reply_at', nowIso_());

      // stop future auto follow-up on replied threads unless Mariam re-opens
      setValue_(sheet, rowNum, headers, 'approval_status', 'PENDING_REVIEW');
      setValue_(sheet, rowNum, headers, 'next_followup_date', '');
      replyEvents.push(`REPLY: ${track} | ${company} | ${contactName}`);
    } catch (err) {
      // Keep silent; not mission critical.
      Logger.log(`Reply sync error row ${rowNum}: ${err}`);
    }
  }

  if (replyEvents.length) {
    notifyDiscord_('New Outreach Replies Detected', replyEvents, { mentionMariam: true });
  }
}

function setDiscordWebhookUrl(url) {
  const value = String(url || '').trim();
  if (!value.startsWith('https://discord.com/api/webhooks/')) {
    throw new Error('Invalid Discord webhook URL format.');
  }
  PropertiesService.getScriptProperties().setProperty(DISCORD_WEBHOOK_PROPERTY, value);
}

function clearDiscordWebhookUrl() {
  PropertiesService.getScriptProperties().deleteProperty(DISCORD_WEBHOOK_PROPERTY);
}

function setDiscordMariamRoleId(roleId) {
  const value = String(roleId || '').trim();
  if (!value) {
    throw new Error('Role ID cannot be empty.');
  }
  PropertiesService.getScriptProperties().setProperty(DISCORD_MARIAM_ROLE_ID_PROPERTY, value);
}

function clearDiscordMariamRoleId() {
  PropertiesService.getScriptProperties().deleteProperty(DISCORD_MARIAM_ROLE_ID_PROPERTY);
}

function setDiscordBotToken(token) {
  const value = String(token || '').trim();
  if (!value) {
    throw new Error('Bot token cannot be empty.');
  }
  PropertiesService.getScriptProperties().setProperty(DISCORD_BOT_TOKEN_PROPERTY, value);
}

function clearDiscordBotToken() {
  PropertiesService.getScriptProperties().deleteProperty(DISCORD_BOT_TOKEN_PROPERTY);
}

function setDiscordCommandChannelIds(channelIdsCsv) {
  const value = String(channelIdsCsv || '').trim();
  if (!value) {
    throw new Error('Channel IDs cannot be empty.');
  }
  const parsed = splitCsv_(value).filter(isSnowflakeId_);
  if (!parsed.length) {
    throw new Error('No valid channel IDs found.');
  }
  PropertiesService.getScriptProperties().setProperty(DISCORD_COMMAND_CHANNEL_IDS_PROPERTY, parsed.join(','));
}

function clearDiscordCommandChannelIds() {
  PropertiesService.getScriptProperties().deleteProperty(DISCORD_COMMAND_CHANNEL_IDS_PROPERTY);
}

function setDiscordAllowedUserIds(userIdsCsv) {
  const value = String(userIdsCsv || '').trim();
  if (!value) {
    throw new Error('User IDs cannot be empty.');
  }
  const parsed = splitCsv_(value).filter(isSnowflakeId_);
  if (!parsed.length) {
    throw new Error('No valid user IDs found.');
  }
  PropertiesService.getScriptProperties().setProperty(DISCORD_ALLOWED_USER_IDS_PROPERTY, parsed.join(','));
}

function clearDiscordAllowedUserIds() {
  PropertiesService.getScriptProperties().deleteProperty(DISCORD_ALLOWED_USER_IDS_PROPERTY);
}

function testDiscordNotification() {
  notifyDiscord_('Kiroku Outreach Bot Connected', [`Sheet: ${SHEET_NAME}`, `Time: ${nowIso_()}`], {
    mentionMariam: false
  });
}

function testDiscordBotMessage() {
  const channelIds = getDiscordCommandChannelIds_();
  if (!channelIds.length) {
    throw new Error('No command channels configured.');
  }
  postDiscordBotMessage_(channelIds[0], `Kiroku command bridge online at ${nowIso_()}`);
}

function bootstrapDiscordCommandCursor() {
  const channelIds = getDiscordCommandChannelIds_();
  const token = getDiscordBotToken_();
  if (!token) {
    throw new Error('Discord bot token not configured.');
  }
  if (!channelIds.length) {
    throw new Error('Discord command channels not configured.');
  }

  const props = PropertiesService.getScriptProperties();
  channelIds.forEach((channelId) => {
    const latest = fetchDiscordMessages_(token, channelId, null, 1);
    if (!latest.length) return;
    props.setProperty(lastMsgPropertyKey_(channelId), String(latest[0].id));
  });
}

function pollDiscordCommands() {
  const token = getDiscordBotToken_();
  if (!token) {
    throw new Error('Discord bot token not configured.');
  }

  const channelIds = getDiscordCommandChannelIds_();
  if (!channelIds.length) {
    throw new Error('Discord command channels not configured.');
  }

  channelIds.forEach((channelId) => {
    processDiscordChannelCommands_(token, channelId);
  });
}

function processDiscordChannelCommands_(token, channelId) {
  const props = PropertiesService.getScriptProperties();
  const lastId = props.getProperty(lastMsgPropertyKey_(channelId));
  if (!lastId) {
    const latest = fetchDiscordMessages_(token, channelId, null, 1);
    if (latest.length) {
      props.setProperty(lastMsgPropertyKey_(channelId), String(latest[0].id));
    }
    return;
  }

  const messages = fetchDiscordMessages_(token, channelId, lastId, 50)
    .filter((m) => m && m.id)
    .sort((a, b) => compareSnowflake_(a.id, b.id));

  if (!messages.length) return;

  let newestId = lastId || '';
  messages.forEach((message) => {
    if (compareSnowflake_(message.id, newestId) > 0) {
      newestId = String(message.id);
    }
    handleDiscordCommandMessage_(token, channelId, message);
  });

  if (newestId) {
    props.setProperty(lastMsgPropertyKey_(channelId), newestId);
  }
}

function handleDiscordCommandMessage_(token, channelId, message) {
  if (!message || !message.content) return;
  if (message.author && message.author.bot) return;

  const raw = String(message.content || '').trim();
  if (!raw.toLowerCase().startsWith(DISCORD_COMMAND_PREFIX)) return;

  const payload = raw.slice(DISCORD_COMMAND_PREFIX.length).trim();
  const args = payload ? payload.split(/\s+/) : [];
  const command = (args.shift() || 'help').toLowerCase();
  const userId = String((message.author && message.author.id) || '').trim();
  const username = String((message.author && message.author.username) || 'unknown').trim();

  try {
    if (requiresAdminCommand_(command) && !isAllowedDiscordUser_(userId)) {
      postDiscordBotMessage_(channelId, `<@${userId}> Unauthorized for command \`${command}\`.`);
      return;
    }

    const response = executeDiscordCommand_(command, args, {
      userId,
      username
    });

    if (response) {
      postDiscordBotMessage_(channelId, response);
    }
  } catch (err) {
    const errorMsg = truncate_(String(err), 800);
    postDiscordBotMessage_(channelId, `<@${userId}> command failed: \`${errorMsg}\``);
  }
}

function executeDiscordCommand_(command, args, actor) {
  switch (command) {
    case 'help':
      return [
        `Kiroku commands (${DISCORD_COMMAND_PREFIX} ...):`,
        '`help`',
        '`status`',
        '`queue [N]`',
        '`row <sequence>`',
        '`approve <seq_csv>`',
        '`reject <seq_csv>`',
        '`unlock <seq_csv>`',
        '`lock <seq_csv>`',
        '`run-send`',
        '`run-replies`',
        '`next`'
      ].join('\n');
    case 'status':
      return buildOutreachStatusSummary_();
    case 'queue':
      return buildQueueSummary_(args[0]);
    case 'row':
      return buildRowSummary_(args[0]);
    case 'next':
      return buildNextActionSummary_();
    case 'approve':
      return batchUpdateRows_(args[0], actor, (sheet, headers, rowNum) => {
        setValue_(sheet, rowNum, headers, 'approval_status', 'APPROVED');
        setValue_(sheet, rowNum, headers, 'approved_by', `Discord:${actor.username}`);
        setValue_(sheet, rowNum, headers, 'approved_at', nowIso_());
      }, 'approved');
    case 'reject':
      return batchUpdateRows_(args[0], actor, (sheet, headers, rowNum) => {
        setValue_(sheet, rowNum, headers, 'approval_status', 'REJECTED');
        setValue_(sheet, rowNum, headers, 'approved_by', `Discord:${actor.username}`);
        setValue_(sheet, rowNum, headers, 'approved_at', nowIso_());
      }, 'rejected');
    case 'unlock':
      return batchUpdateRows_(args[0], actor, (sheet, headers, rowNum) => {
        setValue_(sheet, rowNum, headers, 'send_lock', 'UNLOCKED');
      }, 'unlocked');
    case 'lock':
      return batchUpdateRows_(args[0], actor, (sheet, headers, rowNum) => {
        setValue_(sheet, rowNum, headers, 'send_lock', 'LOCKED');
      }, 'locked');
    case 'run-send':
      sendApprovedDueEmails();
      return `Send run executed at ${nowIso_()}.`;
    case 'run-replies':
      syncRepliesByThread();
      return `Reply sync executed at ${nowIso_()}.`;
    default:
      return `Unknown command \`${command}\`. Use \`${DISCORD_COMMAND_PREFIX} help\`.`;
  }
}

function requiresAdminCommand_(command) {
  return ['approve', 'reject', 'unlock', 'lock', 'run-send', 'run-replies'].indexOf(command) >= 0;
}

function isAllowedDiscordUser_(userId) {
  const allowed = getDiscordAllowedUserIds_();
  if (!allowed.length) return false;
  return allowed.indexOf(String(userId || '').trim()) >= 0;
}

function batchUpdateRows_(seqCsv, actor, mutatorFn, verb) {
  const sequences = parseSequenceCsv_(seqCsv);
  if (!sequences.length) {
    throw new Error('No valid sequence ids provided.');
  }

  const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error(`Sheet ${SHEET_NAME} not found`);
  const headers = getHeaders_(sheet);
  const data = getRows_(sheet);
  const seqIndex = buildSequenceIndex_(headers, data);

  const updated = [];
  const missing = [];
  sequences.forEach((seq) => {
    const rowNum = seqIndex[seq];
    if (!rowNum) {
      missing.push(seq);
      return;
    }
    mutatorFn(sheet, headers, rowNum);
    updated.push(seq);
  });

  const parts = [`${verb.toUpperCase()} by ${actor.username}: ${updated.join(', ') || 'none'}`];
  if (missing.length) parts.push(`missing: ${missing.join(', ')}`);
  return parts.join(' | ');
}

function buildOutreachStatusSummary_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error(`Sheet ${SHEET_NAME} not found`);
  const headers = getHeaders_(sheet);
  const data = getRows_(sheet);

  let total = 0;
  let approved = 0;
  let pending = 0;
  let rejected = 0;
  let unlocked = 0;
  let locked = 0;
  let replied = 0;
  let notSent = 0;

  data.forEach((row) => {
    total += 1;
    const approval = String(getValue_(row, headers, 'approval_status')).trim();
    const lock = String(getValue_(row, headers, 'send_lock')).trim();
    const sendStatus = String(getValue_(row, headers, 'send_status')).trim();
    const reply = String(getValue_(row, headers, 'reply_status')).trim();
    if (approval === 'APPROVED') approved += 1;
    if (approval === 'PENDING_REVIEW') pending += 1;
    if (approval === 'REJECTED') rejected += 1;
    if (lock === 'UNLOCKED') unlocked += 1;
    if (lock === 'LOCKED') locked += 1;
    if (sendStatus === 'NOT_SENT') notSent += 1;
    if (reply && reply !== 'NO_REPLY') replied += 1;
  });

  return [
    `Outreach status (${SHEET_NAME})`,
    `total=${total} approved=${approved} pending=${pending} rejected=${rejected}`,
    `unlocked=${unlocked} locked=${locked}`,
    `not_sent=${notSent} replied=${replied}`
  ].join('\n');
}

function buildQueueSummary_(limitArg) {
  const limit = Math.max(1, Math.min(20, Number(limitArg || 5) || 5));
  const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error(`Sheet ${SHEET_NAME} not found`);
  const headers = getHeaders_(sheet);
  const data = getRows_(sheet);

  const rows = data
    .map((row) => ({
      sequence: String(getValue_(row, headers, 'sequence')).trim(),
      company: String(getValue_(row, headers, 'company')).trim(),
      contact: String(getValue_(row, headers, 'decision_maker_name')).trim(),
      track: String(getValue_(row, headers, 'track')).trim(),
      lock: String(getValue_(row, headers, 'send_lock')).trim(),
      approval: String(getValue_(row, headers, 'approval_status')).trim(),
      touch: String(getValue_(row, headers, 'active_touch')).trim(),
      send: String(getValue_(row, headers, 'send_status')).trim()
    }))
    .sort((a, b) => Number(a.sequence) - Number(b.sequence))
    .slice(0, limit);

  const lines = rows.map((r) =>
    `#${r.sequence} ${r.track} ${r.company} (${r.contact}) | ${r.lock} | ${r.approval} | ${r.touch}/${r.send}`
  );
  return ['Queue snapshot:', ...lines].join('\n');
}

function buildRowSummary_(sequenceArg) {
  const sequence = String(sequenceArg || '').trim();
  if (!sequence) {
    throw new Error('Usage: row <sequence>');
  }

  const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error(`Sheet ${SHEET_NAME} not found`);
  const headers = getHeaders_(sheet);
  const data = getRows_(sheet);
  const seqIndex = buildSequenceIndex_(headers, data);
  const rowNum = seqIndex[sequence];
  if (!rowNum) {
    return `Row ${sequence} not found.`;
  }

  const row = sheet.getRange(rowNum, 1, 1, sheet.getLastColumn()).getValues()[0];
  const summary = [
    `Row #${sequence} summary`,
    `company=${String(getValue_(row, headers, 'company')).trim()}`,
    `contact=${String(getValue_(row, headers, 'decision_maker_name')).trim()}`,
    `track=${String(getValue_(row, headers, 'track')).trim()}`,
    `lock=${String(getValue_(row, headers, 'send_lock')).trim()}`,
    `approval=${String(getValue_(row, headers, 'approval_status')).trim()}`,
    `active_touch=${String(getValue_(row, headers, 'active_touch')).trim()}`,
    `send_status=${String(getValue_(row, headers, 'send_status')).trim()}`,
    `reply_status=${String(getValue_(row, headers, 'reply_status')).trim()}`
  ];
  return summary.join('\n');
}

function buildNextActionSummary_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error(`Sheet ${SHEET_NAME} not found`);
  const headers = getHeaders_(sheet);
  const data = getRows_(sheet);

  const actionable = data
    .map((row) => ({
      sequence: String(getValue_(row, headers, 'sequence')).trim(),
      company: String(getValue_(row, headers, 'company')).trim(),
      lock: String(getValue_(row, headers, 'send_lock')).trim(),
      approval: String(getValue_(row, headers, 'approval_status')).trim(),
      touch: String(getValue_(row, headers, 'active_touch')).trim(),
      send: String(getValue_(row, headers, 'send_status')).trim(),
      next: String(getValue_(row, headers, 'next_followup_date')).trim()
    }))
    .filter((r) => r.lock === 'UNLOCKED' && r.approval === 'APPROVED' && r.send === 'NOT_SENT')
    .sort((a, b) => Number(a.sequence) - Number(b.sequence));

  if (!actionable.length) {
    return 'No approved+unlocked pending rows ready for send.';
  }

  const lines = actionable.map((r) =>
    `#${r.sequence} ${r.company} | ${r.touch} | next=${r.next || 'n/a'}`
  );
  return ['Ready-to-send rows:', ...lines].join('\n');
}

function getHeaders_(sheet) {
  const headerVals = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const headers = {};
  for (let c = 0; c < headerVals.length; c++) {
    headers[String(headerVals[c]).trim()] = c + 1;
  }
  return headers;
}

function getRows_(sheet) {
  if (sheet.getLastRow() < 2) return [];
  return sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getValues();
}

function getValue_(row, headers, key) {
  const col = headers[key];
  if (!col) return '';
  return row[col - 1];
}

function setValue_(sheet, rowNum, headers, key, value) {
  const col = headers[key];
  if (!col) return;
  sheet.getRange(rowNum, col).setValue(value);
}

function todayYmd_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

function nowIso_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd'T'HH:mm:ss");
}

function notifyDiscord_(title, lines, options) {
  const webhook = getDiscordWebhookUrl_();
  if (!webhook) return;

  const opts = options || {};
  const roleId = getDiscordMariamRoleId_();
  const mention = opts.mentionMariam && roleId ? `<@&${roleId}> ` : '';
  const body = [mention + `**${title}**`]
    .concat((lines || []).map((line) => `- ${line}`))
    .join('\n');

  const payload = { content: truncate_(body, 1900) };
  UrlFetchApp.fetch(webhook, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}

function getDiscordWebhookUrl_() {
  return PropertiesService.getScriptProperties().getProperty(DISCORD_WEBHOOK_PROPERTY);
}

function getDiscordMariamRoleId_() {
  return PropertiesService.getScriptProperties().getProperty(DISCORD_MARIAM_ROLE_ID_PROPERTY);
}

function getDiscordBotToken_() {
  return String(PropertiesService.getScriptProperties().getProperty(DISCORD_BOT_TOKEN_PROPERTY) || '').trim();
}

function getDiscordCommandChannelIds_() {
  return splitCsv_(PropertiesService.getScriptProperties().getProperty(DISCORD_COMMAND_CHANNEL_IDS_PROPERTY));
}

function getDiscordAllowedUserIds_() {
  return splitCsv_(PropertiesService.getScriptProperties().getProperty(DISCORD_ALLOWED_USER_IDS_PROPERTY));
}

function splitCsv_(value) {
  return String(value || '')
    .split(',')
    .map((v) => v.trim())
    .filter((v) => Boolean(v));
}

function parseSequenceCsv_(value) {
  return splitCsv_(value)
    .map((v) => v.replace(/[^\d]/g, ''))
    .filter((v) => Boolean(v));
}

function isSnowflakeId_(value) {
  return /^\d{10,25}$/.test(String(value || '').trim());
}

function compareSnowflake_(a, b) {
  const left = String(a || '').trim();
  const right = String(b || '').trim();
  if (!left && !right) return 0;
  if (!left) return -1;
  if (!right) return 1;
  if (left.length !== right.length) return left.length - right.length;
  if (left === right) return 0;
  return left < right ? -1 : 1;
}

function lastMsgPropertyKey_(channelId) {
  return `${DISCORD_LAST_MSG_PREFIX}${String(channelId).trim()}`;
}

function fetchDiscordMessages_(token, channelId, afterId, limit) {
  const lim = Math.max(1, Math.min(100, Number(limit || 50) || 50));
  let url = `https://discord.com/api/v10/channels/${encodeURIComponent(channelId)}/messages?limit=${lim}`;
  if (afterId) {
    url += `&after=${encodeURIComponent(afterId)}`;
  }

  const response = UrlFetchApp.fetch(url, {
    method: 'get',
    headers: {
      Authorization: `Bot ${token}`
    },
    muteHttpExceptions: true
  });
  const code = Number(response.getResponseCode());
  if (code < 200 || code >= 300) {
    throw new Error(`Discord fetch messages failed: HTTP ${code}`);
  }
  return JSON.parse(response.getContentText() || '[]');
}

function postDiscordBotMessage_(channelId, content) {
  const token = getDiscordBotToken_();
  if (!token) {
    throw new Error('Discord bot token not configured.');
  }
  const url = `https://discord.com/api/v10/channels/${encodeURIComponent(channelId)}/messages`;
  const payload = {
    content: truncate_(String(content || ''), 1900)
  };
  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: `Bot ${token}`
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
  const code = Number(response.getResponseCode());
  if (code < 200 || code >= 300) {
    throw new Error(`Discord post message failed: HTTP ${code}`);
  }
}

function buildSequenceIndex_(headers, data) {
  const index = {};
  data.forEach((row, i) => {
    const sequence = String(getValue_(row, headers, 'sequence')).trim();
    if (!sequence) return;
    index[sequence] = i + 2;
  });
  return index;
}

function truncate_(text, limit) {
  const value = String(text || '');
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 3)}...`;
}
