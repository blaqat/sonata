local vim = vim

function set_env()
	vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<space>vc", true, false, true), "x", true)
end

return {
	theme = "aylin",
	ui = "dark",
	run = "sonata",
	font = {
		family = "Monaspace Krypton Var",
		size = 14,
		fallbacks = { "Mononoki Nerd Font" },
	},
	lua = {
		set_env,
	},
}
