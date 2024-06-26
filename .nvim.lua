local vim = vim

local function set_env()
	vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<space>vc", true, false, true), "x", true)
end

return {
	theme = "catppuccin46",
	highlight = {
		misc = { ["Constant"] = "bold" },
	},
	-- theme = "aylin",
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
