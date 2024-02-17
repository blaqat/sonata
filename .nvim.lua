return {
	theme = "aylin",
	font = {
		family = "Monaspace Krypton Var",
		size = 14,
		fallbacks = { "Mononoki Nerd Font" },
	},
	lua = {
		'vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<space>vc", true, false, true), "x", true)',
	},
}
